import math
import os
import re
from asyncio import Lock
from io import BytesIO
from pathlib import Path
from random import SystemRandom

import aiohttp
import soundfile
from PIL import Image
from nonebot import on_message, on_regex
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment

from util.Data import (
    get_alias_list_lxns,
    get_alias_list_ycn,
    get_alias_list_xray,
    get_music_data,
)
from .database import openchars
from .ranking import ranking
from .times import times
from .utils import generate_message_state, check_music_id, generate_success_state

random = SystemRandom()

lock = Lock()

start_open_chars = on_regex(r"^dlx猜歌$", re.I)
open_chars = on_regex(r"^开\s*.+$")
all_message_handle = on_message(block=False)
pass_game = on_regex(r"^(结束猜歌|将大局逆转吧)$")
info_tip = on_regex(r"^(提示|提醒|信息)\s*[1-5]?$")
pic_tip = on_regex(r"^(封面|曲绘|图片?)\s*[1-5]?$")
aud_tip = on_regex(r"^(音(乐|频)|(乐|歌)曲|片段)\s*[1-5]?$")
rank = on_regex(r"^(迪拉熊|dlx)猜歌(排行榜?|榜)$", re.I)
rank_i = on_regex(r"^(迪拉熊|dlx)猜歌(个人)?排名$", re.I)


# 根据乐曲别名查询乐曲id列表
async def find_songid_by_alias(name, song_list):
    # 芝士id列表
    matched_ids = list()

    # 芝士查找
    for info in song_list:
        if name.casefold() == info["title"].casefold() or name == info["id"]:
            matched_ids.append(info["id"])

    alias_list = await get_alias_list_lxns()
    for info in alias_list["aliases"]:
        if str(info["song_id"]) in matched_ids:
            continue
        for alias in info["aliases"]:
            if name.casefold() == alias.casefold():
                matched_ids.append(str(info["song_id"]))
                break

    alias_list = await get_alias_list_xray()
    for id, info in alias_list.items():
        if str(id) in matched_ids:
            continue
        for alias in info:
            if name.casefold() == alias.casefold():
                matched_ids.append(str(id))
                break

    alias_list = await get_alias_list_ycn()
    for info in alias_list["content"]:
        if str(info["SongID"]) in matched_ids:
            continue
        for alias in info["Alias"]:
            if name.casefold() == alias.casefold():
                matched_ids.append(str(info["SongID"]))
                break

    # 芝士排序
    # sorted_matched_ids = sorted(matched_ids, key=int)

    # 芝士输出
    return matched_ids


@start_open_chars.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    async with lock:
        game_data = await openchars.start(group_id)
        _, game_state, _, game_data = generate_message_state(game_data, user_id)

    await start_open_chars.send(
        "本轮开字母游戏要开始了哟~\r\n□：字母或数字\r\n○：假名或汉字\r\n☆：符号\r\n\r\n发送“开+文字”开出字母\r\n发送“提示（+行号）”获取提示（每首5次机会）\r\n发送“封面（+行号）”获取部分封面（每首2次机会）\r\n发送“歌曲（+行号）”获取1秒歌曲片段（每首1次机会）\r\n发送“结束猜歌”结束\r\n发送歌名或别名即可尝试猜歌"
    )
    await start_open_chars.send(game_state)


@open_chars.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    msg = event.get_plaintext()
    match = re.fullmatch(r"开\s*(.+)", msg)
    if not match:
        return

    char = match.group(1)
    async with lock:
        not_opened, game_data = openchars.open_char(group_id, char, user_id)
        if not_opened is None:
            return

        if not not_opened:
            await open_chars.send(
                (
                    MessageSegment.at(user_id),
                    MessageSegment.text(" "),
                    MessageSegment.text("这个字已经开过了哦，换一个吧~"),
                    MessageSegment.image(Path("./Static/Wordle/1.png")),
                )
            )
            return

        is_game_over, game_state, char_all_open, game_data = generate_message_state(
            game_data, user_id
        )
        await openchars.update_game_data(group_id, game_data)
        if char_all_open:
            for i, title, id in char_all_open:
                cover_path = f"./Cache/Jacket/{id % 10000}.png"
                if not os.path.exists(cover_path):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"https://assets2.lxns.net/maimai/jacket/{id % 10000}.png"
                        ) as resp:
                            with open(cover_path, "wb") as fd:
                                async for chunk in resp.content.iter_chunked(1024):
                                    fd.write(chunk)

                await open_chars.send(
                    (
                        MessageSegment.at(user_id),
                        MessageSegment.text(" "),
                        MessageSegment.text(f"猜对了！第{i}行的歌曲是"),
                        MessageSegment.image(Path(cover_path)),
                        MessageSegment.text(title),
                    )
                )

        await open_chars.send(game_state)
        if is_game_over:
            openchars.game_over(group_id)
            await open_chars.send(
                "全部答对啦，恭喜各位🎉\r\n可以发送“dlx猜歌”再次游玩mai~"
            )


@all_message_handle.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    async with lock:
        game_data = openchars.get_game_data(group_id)
        if not game_data:
            return

        msg_content = event.get_plaintext()
        if not msg_content:
            return

        songList = await get_music_data()
        music_ids = await find_songid_by_alias(msg_content, songList)
        if not music_ids:
            return

        guess_success, game_data = check_music_id(game_data, music_ids, user_id)
        if not guess_success:
            return

        for i, title, id in guess_success:
            cover_path = f"./Cache/Jacket/{id % 10000}.png"
            if not os.path.exists(cover_path):
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"https://assets2.lxns.net/maimai/jacket/{id % 10000}.png"
                    ) as resp:
                        with open(cover_path, "wb") as fd:
                            async for chunk in resp.content.iter_chunked(1024):
                                fd.write(chunk)

            await all_message_handle.send(
                (
                    MessageSegment.at(user_id),
                    MessageSegment.text(" "),
                    MessageSegment.text(f"猜对了！第{i}行的歌曲是"),
                    MessageSegment.image(Path(cover_path)),
                    MessageSegment.text(title),
                )
            )
        is_game_over, game_state, _, game_data = generate_message_state(
            game_data, user_id
        )
        await start_open_chars.send(game_state)
        if is_game_over:
            openchars.game_over(group_id)
            await start_open_chars.send(
                "全部答对啦，恭喜各位🎉\r\n可以发送“dlx猜歌”再次游玩mai~"
            )
        else:
            await openchars.update_game_data(group_id, game_data)


@pass_game.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    async with lock:
        game_data = openchars.get_game_data(group_id)
        if not game_data:
            return

        openchars.game_over(group_id)

    await pass_game.send(generate_success_state(game_data))
    await pass_game.send("本轮猜歌结束了，可以发送“dlx猜歌”再次游玩mai~")


@info_tip.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    msg = event.get_plaintext()
    index = re.search(r"\d+", msg)
    async with lock:
        game_data = await openchars.get_game_data(group_id)
        if not game_data:
            return

        if index:
            index = int(index.group()) - 1
            data = game_data["game_contents"][index]
        else:
            game_contents = [
                d
                for d in game_data["game_contents"]
                if not d["is_correct"] and d["tips"]
            ]
            if not game_contents:
                await info_tip.send(
                    (
                        MessageSegment.text("所有歌曲的信息提示次数都已经用完了mai~"),
                        MessageSegment.image(Path("./Static/Wordle/1.png")),
                    )
                )
                return

            data = random.choice(game_contents)

        if data["is_correct"]:
            await info_tip.send(
                (
                    MessageSegment.text(f"第{data["index"]}行的歌曲已经猜对了mai~"),
                    MessageSegment.image(Path("./Static/Wordle/1.png")),
                )
            )
            return

        tips = {
            "紫谱等级": lambda s: s["level"][3 if len(s["level"]) >= 5 else -1],
            "紫谱谱师": lambda s: s["charts"][3 if len(s["charts"]) >= 5 else -1][
                "charter"
            ],
            "曲师": lambda s: s["basic_info"]["artist"],
            "分类": lambda s: s["basic_info"]["genre"],
            "BPM": lambda s: s["basic_info"]["bpm"],
            "初出版本": lambda s: s["basic_info"]["from"],
        }

        tip_keys = [d for d in tips.keys() if d not in data["tips"]]
        if not tip_keys:
            await info_tip.send(
                (
                    MessageSegment.text(
                        f"第{data["index"]}行的歌曲信息提示次数用完了mai~"
                    ),
                    MessageSegment.image(Path("./Static/Wordle/1.png")),
                )
            )
            return

        songList = await get_music_data()
        song = [d for d in songList if d["id"] == str(data["music_id"])]
        if len(song) != 1:
            await info_tip.send(
                (
                    MessageSegment.text(
                        f"第{data["index"]}行的歌曲信息提示次数用完了mai~"
                    ),
                    MessageSegment.image(Path("./Static/Wordle/1.png")),
                )
            )
            return

        data["part"].add(user_id)
        tip_key = random.choice(tip_keys)
        data["tips"].append(tip_key)
        await openchars.update_game_data(group_id, game_data)

    tip_info = tips[tip_key](song[0])
    await info_tip.send(f"第{data["index"]}行的歌曲{tip_key}是{tip_info}mai~")


@pic_tip.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    msg = event.get_plaintext()
    index = re.search(r"\d+", msg)
    async with lock:
        game_data = await openchars.get_game_data(group_id)
        if not game_data:
            return

        if index:
            index = int(index.group()) - 1
            data = game_data["game_contents"][index]
        else:
            game_contents = [
                d
                for d in game_data["game_contents"]
                if not d["is_correct"] and d["pic_times"] < 2
            ]
            if not game_contents:
                await pic_tip.send(
                    (
                        MessageSegment.text("所有歌曲的封面提示次数都已经用完了mai~"),
                        MessageSegment.image(Path("./Static/Wordle/1.png")),
                    )
                )
                return

            data = random.choice(game_contents)

        if data["is_correct"]:
            await pic_tip.send(
                (
                    MessageSegment.text(f"第{data["index"]}行的歌曲已经猜对了mai~"),
                    MessageSegment.image(Path("./Static/Wordle/1.png")),
                )
            )
            return

        if data["pic_times"] >= 2:
            await pic_tip.send(
                (
                    MessageSegment.text(f"第{data["index"]}行的封面提示次数用完了mai~"),
                    MessageSegment.image(Path("./Static/Wordle/1.png")),
                )
            )
            return

        data["part"].add(user_id)
        data["pic_times"] += 1
        await openchars.update_game_data(group_id, game_data)

    await pic_tip.send(
        (
            MessageSegment.at(user_id),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    cover_path = f"./Cache/Jacket/{data["music_id"] % 10000}.png"
    if not os.path.exists(cover_path):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://assets2.lxns.net/maimai/jacket/{data["music_id"] % 10000}.png"
            ) as resp:
                with open(cover_path, "wb") as fd:
                    async for chunk in resp.content.iter_chunked(1024):
                        fd.write(chunk)

    cover = Image.open(cover_path)
    pers = 1 / math.sqrt(random.randint(16, 25))
    size_x = math.ceil(cover.height * pers)
    size_y = math.ceil(cover.width * pers)
    pos_x = random.randint(0, cover.height - size_x)
    pos_y = random.randint(0, cover.width - size_y)
    pice = cover.crop((pos_x, pos_y, pos_x + size_x, pos_y + size_y))
    pice = pice.resize((480, 480), Image.Resampling.LANCZOS)
    img_byte_arr = BytesIO()
    pice.save(img_byte_arr, format="PNG", optimize=True)
    img_byte_arr.seek(0)
    img_bytes = img_byte_arr.getvalue()
    await pic_tip.send(
        (
            MessageSegment.text(f"第{data["index"]}行的歌曲部分封面是"),
            MessageSegment.image(img_bytes),
        )
    )


@aud_tip.handle()
async def _(event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    msg = event.get_plaintext()
    index = re.search(r"\d+", msg)
    async with lock:
        game_data = await openchars.get_game_data(group_id)
        if not game_data:
            return

        if index:
            index = int(index.group()) - 1
            data = game_data["game_contents"][index]
        else:
            game_contents = [
                d
                for d in game_data["game_contents"]
                if not d["is_correct"] and d["aud_times"] < 1
            ]
            if not game_contents:
                await aud_tip.send(
                    (
                        MessageSegment.text("所有歌曲的歌曲提示次数都已经用完了mai~"),
                        MessageSegment.image(Path("./Static/Wordle/1.png")),
                    )
                )
                return

            data = random.choice(game_contents)

        if data["is_correct"]:
            await aud_tip.send(
                (
                    MessageSegment.text(f"第{data["index"]}行的歌曲已经猜对了mai~"),
                    MessageSegment.image(Path("./Static/Wordle/1.png")),
                )
            )
            return

        if data["aud_times"] >= 1:
            await aud_tip.send(
                (
                    MessageSegment.text(f"第{data["index"]}行的歌曲提示次数用完了mai~"),
                    MessageSegment.image(Path("./Static/Wordle/1.png")),
                )
            )
            return

        data["part"].add(user_id)
        data["aud_times"] += 1
        await openchars.update_game_data(group_id, game_data)

    await aud_tip.send(
        (
            MessageSegment.at(user_id),
            MessageSegment.text(" "),
            MessageSegment.text(
                f"迪拉熊正在准备播放第{data["index"]}行的歌曲，稍等一下mai~"
            ),
        )
    )
    music_path = f"./Cache/Music/{data["music_id"] % 10000}.mp3"
    if not os.path.exists(music_path):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://assets2.lxns.net/maimai/music/{data["music_id"] % 10000}.mp3"
            ) as resp:
                with open(music_path, "wb") as fd:
                    async for chunk in resp.content.iter_chunked(1024):
                        fd.write(chunk)

    audio_data, samplerate = soundfile.read(music_path)
    pos = random.randint(0, len(audio_data) - samplerate)
    audio = audio_data[pos : pos + samplerate]
    aud_byte_arr = BytesIO()
    soundfile.write(aud_byte_arr, audio, samplerate, format="MP3")
    aud_byte_arr.seek(0)
    aud_bytes = aud_byte_arr.getvalue()
    await aud_tip.send(MessageSegment.record(aud_bytes))


@rank.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    scores = ranking.get_avg_scores()
    leaderboard = [
        (qq, achi, _times) for qq, achi, _times in scores if times.check_available(qq)
    ]
    leaderboard_output = list()
    current_score, current_index = 0, 0
    for i, (qq, achi, _times) in enumerate(leaderboard, start=1):
        if achi < current_score or current_score <= 0:
            current_index = i
            current_score = achi

        user_name = (await bot.get_stranger_info(user_id=qq))["nickname"]
        rank_str = f"{current_index}. {user_name}：{math.trunc(achi * 1000000) / 1000000:.4%} × {_times}"
        leaderboard_output.append(rank_str)
        if len(leaderboard_output) > 9:
            break

    avg = sum(d[1] for d in scores) / len(scores) if len(scores) > 0 else 0
    msg = "\r\n".join(leaderboard_output)
    msg = f"猜歌准确率排行榜Top{len(leaderboard_output)}：\r\n{msg}\r\n\r\n上榜人数：{len(leaderboard)}/{len(scores)}\r\n平均达成率：{math.trunc(avg * 1000000) / 1000000:.4%}\r\n\r\n注：若长时间不参与猜歌游戏，将不计入排行榜，重新参与十首歌即可恢复排名。"
    await rank.send(msg)


@rank_i.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    user_id = event.user_id
    scores = ranking.get_avg_scores()
    leaderboard = [
        (qq, achi, _times) for qq, achi, _times in scores if times.check_available(qq)
    ]
    leaderboard_output = list()
    index = -1
    for i, (qq, achi, _times) in enumerate(leaderboard):
        if qq == str(user_id):
            index = i
            break

    if index >= 0:
        current_score, current_index = leaderboard[0][1], 0
        h_count = 2 if index > 2 else index
        t_count = 2 if len(leaderboard) - index > 2 else len(leaderboard) - index - 1
        pand = h_count + t_count
        s_index = index + 2 - pand
        e_index = index - 2 + pand
        for i, (qq, achi, _times) in enumerate(leaderboard):
            if i > e_index:
                break

            if achi < current_score or current_score <= 0:
                current_index = i + 1
                current_score = achi

            if s_index > i:
                continue

            user_name = (await bot.get_stranger_info(user_id=qq))["nickname"]
            if i == index:
                rank_str = f"{current_index}. {user_name}：{math.trunc(achi * 1000000) / 1000000:.4%}"
            else:
                rank_str = f"{current_index}. {user_name}：{math.trunc(achi * 1000000) / 1000000:.4%} × {_times}"

            leaderboard_output.append(rank_str)

        leaderboard_output.append(f"\r\n游玩次数：{leaderboard[index][2]}")
    else:
        achi, _times = ranking.get_score(user_id)
        leaderboard_output.append(f"\r\n游玩次数：{_times}")

    msg = "\r\n".join(leaderboard_output)
    msg = f"您在排行榜上的位置：\r\n{msg}\r\n\r\n注：若长时间不参与猜歌游戏，将不计入排行榜，重新参与十首歌即可重新上榜。"
    await rank.send(
        MessageSegment.at(user_id), MessageSegment.text(" "), MessageSegment.text(msg)
    )
