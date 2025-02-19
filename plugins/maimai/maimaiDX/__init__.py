import math
import os
import re
import shelve
from pathlib import Path
from random import SystemRandom

import aiohttp
from dill import Pickler, Unpickler
from nonebot import on_fullmatch, on_regex
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment

from util.Data import (
    get_chart_stats,
    get_music_data,
    get_alias_list_lxns,
    get_alias_list_ycn,
    get_alias_list_xray,
)
from util.DivingFish import get_player_data, get_player_records, get_player_record
from .GenB50 import (
    compute_record,
    generateb50,
    generate_wcb,
    get_page_records,
    ratings,
    records_filter,
    find_song_by_id,
    dxscore_proc,
    get_fit_diff,
)
from .MusicInfo import music_info, play_info, utage_music_info, score_info

shelve.Pickler = Pickler
shelve.Unpickler = Unpickler

random = SystemRandom()

best50 = on_regex(r"^dlxb?50(\s*\[CQ:at.*?\]\s*)?$", re.I)
fit50 = on_regex(r"^dlxf50(\s*\[CQ:at.*?\]\s*)?$", re.I)
dxs50 = on_regex(r"^dlxs50(\s*\[CQ:at.*?\]\s*)?$", re.I)
star50 = on_regex(r"^dlxx50(\s*[1-5])+(\s*\[CQ:at.*?\]\s*)?$", re.I)
rate50 = on_regex(
    r"^dlxr50(\s*(s{1,3}(p|\+)?|a{1,3}|b{1,3}|[cd]))+?(\s*\[CQ:at.*?\]\s*)?$",
    re.I,
)
ap50 = on_regex(r"^dlxap(50)?(\s*\[CQ:at.*?\]\s*)?$", re.I)
fc50 = on_regex(r"^dlxfc(50)?(\s*\[CQ:at.*?\]\s*)?$", re.I)
cf50 = on_regex(r"^dlxcf(50)?(\s*\[CQ:at.*?\]\s*)$", re.I)
sd50 = on_regex(r"^dlx(s|f)d(50)?(\s*\[CQ:at.*?\]\s*)?$", re.I)
all50 = on_regex(r"^dlx(all?(50)?|b)(\s*\[CQ:at.*?\]\s*)?$", re.I)
rr50 = on_regex(r"^dlxrr(50)?(\s*\d+)?$", re.I)
sunlist = on_regex(r"^dlx([sc]un|寸|🤏)(\s*\d+?)?$", re.I)
locklist = on_regex(r"^dlx(suo|锁|🔒)(\s*\d+?)?$", re.I)

songinfo = on_regex(r"^(chart|id)\s*((dx|sd|标准?)\s*)?.+$", re.I)
playinfo = on_regex(r"^(score|info)\s*((dx|sd|标准?)\s*)?.+$", re.I)
scoreinfo = on_regex(
    r"^(detail|分数表)\s*(绿|黄|红|紫|白)\s*((dx|sd|标准?)\s*)?.+$", re.I
)
playaudio = on_regex(r"^dlx点歌\s*.+$", re.I)
randomsong = on_regex(r"^随(歌|个|首|张)\s*(绿|黄|红|紫|白)?\s*\d+(\.\d|\+)?$")
maiwhat = on_fullmatch("mai什么", ignorecase=True)

wcb = on_regex(
    r"^(list|完成表)\s*(\d+(\.\d|\+)?|真|超|檄|橙|晓|桃|樱|紫|堇|白|雪|辉|舞|熊|华|爽|煌|宙|星|祭|祝|双)(\s*\d+)?$",
    re.I,
)

whatSong = on_regex(
    r"^((search|查歌)\s*((dx|sd|标准?)\s*)?.+|((dx|sd|标准?)\s*)?.+是什么歌？?)$", re.I
)
aliasSearch = on_regex(r"^((alias|查看?别名)\s*.+|.+有(什么|哪些)别名？?)$")

all_plate = on_regex(r"^(plate|看姓名框)$", re.I)
all_frame = on_regex(r"^(frame|看背景)$", re.I)

set_plate = on_regex(r"^(setplate|设置?姓名框)\s*\d{6}$", re.I)
set_frame = on_regex(r"^(setframe|设置?背景)\s*\d{6}$", re.I)

ratj_on = on_regex(r"^(开启?|启用)分数推荐$")
ratj_off = on_regex(r"^(关闭?|禁用)分数推荐$")

allow_other_on = on_regex(r"^(开启?|启用|允许)代查$")
allow_other_off = on_regex(r"^(关闭?|禁用|禁止)代查$")


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


async def records_to_b50(
    records: list | None,
    songList,
    fc_rules: list | None = None,
    rate_rules: list | None = None,
    is_fit: bool = False,
    is_sd: bool = False,
    is_dxs: bool = False,
    is_all: bool = False,
    dx_star_count: str | None = None,
    rating: int = 0,
):
    sd = list()
    dx = list()
    charts = await get_chart_stats()
    mask_enabled = False
    if not records:
        for song in songList:
            if len(song["id"]) > 5:
                continue
            for i, j in enumerate(song["ds"]):
                record = {
                    "achievements": 101,
                    "ds": j,
                    "dxScore": sum(song["charts"][i]["notes"]) * 3,
                    "fc": "fsdp",
                    "fs": "app",
                    "level": "",
                    "level_index": i,
                    "level_label": [
                        "Basic",
                        "Advanced",
                        "Expert",
                        "Master",
                        "Re:MASTER",
                    ][i],
                    "ra": math.trunc(j * 22.512),
                    "rate": "sssp",
                    "song_id": int(song["id"]),
                    "title": song["title"],
                    "type": song["type"],
                }
                if song["basic_info"]["is_new"]:
                    dx.append(record)
                else:
                    sd.append(record)
        sd = sorted(
            sd, key=lambda x: (x["ra"], x["ds"], x["achievements"]), reverse=True
        )
        dx = sorted(
            dx, key=lambda x: (x["ra"], x["ds"], x["achievements"]), reverse=True
        )
        if rating:
            while (
                sum(d["ra"] for d in sd[:35]) + sum(d["ra"] for d in dx[:15]) > rating
            ):
                if (dx and sd and dx[0]["ra"] > sd[0]["ra"]) or (dx and not sd):
                    dx.pop(0)
                elif sd:
                    sd.pop(0)
        return sd[:35], dx[:15], False
    for record in records:
        if record["level_label"] == "Utage":
            continue
        if fc_rules and record["fc"] not in fc_rules:
            continue
        if rate_rules and record["rate"] not in rate_rules:
            continue
        song_id = record["song_id"]
        song_data = [d for d in songList if d["id"] == str(song_id)][0]
        is_new = song_data["basic_info"]["is_new"]
        fit_diff = get_fit_diff(
            str(record["song_id"]), record["level_index"], record["ds"], charts
        )
        if is_fit or is_sd:
            if record["ra"] == 0:
                continue
            if record["achievements"] > 0 and record["dxScore"] == 0:
                mask_enabled = True
                continue
            record["s_ra"] = record["ds"]
            record["ds"] = math.trunc(fit_diff * 100) / 100
            record["ra"] = math.trunc(
                fit_diff
                * (record["achievements"] if record["achievements"] < 100.5 else 100.5)
                * get_ra_in(record["rate"])
                / 100
            )
            if is_sd:
                record["diff"] = charts["charts"][str(song_id)][record["level_index"]][
                    "std_dev"
                ]
        if is_dxs:
            if record["achievements"] > 0 and record["dxScore"] == 0:
                mask_enabled = True
                continue
            if not dx_star_count:
                song_data = find_song_by_id(str(record["song_id"]), songList)
                record["achievements"] = (
                    record["dxScore"]
                    / (sum(song_data["charts"][record["level_index"]]["notes"]) * 3)
                    * 101
                )
                record["ra"] = math.trunc(
                    record["ds"]
                    * record["achievements"]
                    * get_ra_in(record["rate"])
                    / 100
                )
            else:
                sum_dxscore = (
                    sum(song_data["charts"][record["level_index"]]["notes"]) * 3
                )
                _, stars = dxscore_proc(record["dxScore"], sum_dxscore)
                if str(stars) not in dx_star_count:
                    continue
        if record["ra"] == 0 or record["achievements"] > 101:
            continue
        if is_new or is_all:
            dx.append(record)
        else:
            sd.append(record)
    if is_all:
        all_records = sorted(
            dx, key=lambda x: (x["ra"], x["ds"], x["achievements"]), reverse=True
        )
        dx.clear()
        for record in [
            i
            for i in all_records
            if i["ra"]
            >= all_records[49 if len(all_records) > 50 else len(all_records) - 1]["ra"]
        ]:
            song_id = record["song_id"]
            song_data = [d for d in songList if d["id"] == str(song_id)][0]
            is_new = song_data["basic_info"]["is_new"]
            if is_new:
                dx.append(record)
                all_records.remove(record)
                if len(dx) >= 15:
                    break
        if len(dx) < 15:
            dx.extend(all_records[36 : 51 - len(dx)])
        sd = all_records[:35]
        return sd, dx, mask_enabled
    b35 = sorted(sd, key=lambda x: (x["ra"], x["ds"], x["achievements"]), reverse=True)[
        :35
    ]
    b15 = sorted(dx, key=lambda x: (x["ra"], x["ds"], x["achievements"]), reverse=True)[
        :15
    ]
    if is_sd:
        b35 = sorted(
            b35,
            key=lambda x: (
                x["ds"] >= x["s_ra"],
                x["diff"],
                x["ra"],
                x["ds"],
                x["achievements"],
            ),
            reverse=True,
        )
        b15 = sorted(
            b15,
            key=lambda x: (
                x["ds"] >= x["s_ra"],
                x["diff"],
                x["ra"],
                x["ds"],
                x["achievements"],
            ),
            reverse=True,
        )
    return b35, b15, mask_enabled


async def compare_b50(sender_records, target_records, songList):
    handle_type = len(sender_records) > len(target_records)
    sd = list()
    dx = list()
    mask_enabled = False
    b35, b15, mask_enabled = await records_to_b50(sender_records, songList)
    if not b35 and not b15:
        return sd, dx, mask_enabled
    sd_min = b35[-1]["ra"] if b35 else -1
    dx_min = b15[-1]["ra"] if b15 else -1
    for record in target_records if handle_type else sender_records:
        if record["level_label"] == "Utage":
            continue
        if record["ra"] == 0 or record["achievements"] > 101:
            continue
        if record["achievements"] > 0 and record["dxScore"] == 0:
            mask_enabled = True
            continue
        other_record = [
            d
            for d in (sender_records if handle_type else target_records)
            if d["song_id"] == record["song_id"]
            and d["level_index"] == record["level_index"]
        ]
        if not other_record:
            continue
        other_record = other_record[0]
        if other_record["ra"] == 0 or other_record["achievements"] > 101:
            continue
        if other_record["achievements"] > 0 and other_record["dxScore"] == 0:
            mask_enabled = True
            continue
        song_id = record["song_id"]
        song_data = [d for d in songList if d["id"] == str(song_id)][0]
        is_new = song_data["basic_info"]["is_new"]
        if handle_type:
            record["preferred"] = record["ra"] >= (dx_min if is_new else sd_min)
            record["s_ra"] = other_record["ra"]
            if is_new:
                dx.append(record)
            else:
                sd.append(record)
        else:
            other_record["preferred"] = other_record["ra"] >= (
                dx_min if is_new else sd_min
            )
            other_record["s_ra"] = record["ra"]
            if is_new:
                dx.append(other_record)
            else:
                sd.append(other_record)
    b35 = sorted(
        sd,
        key=lambda x: (x["preferred"], x["ra"] - x["s_ra"], x["ds"], x["achievements"]),
        reverse=True,
    )[:35]
    b15 = sorted(
        dx,
        key=lambda x: (x["preferred"], x["ra"] - x["s_ra"], x["ds"], x["achievements"]),
        reverse=True,
    )[:15]
    return b35, b15, mask_enabled


def get_ra_in(rate: str) -> float:
    return ratings[rate][1]


async def get_info_by_name(name, music_type, songList):
    rep_ids = await find_songid_by_alias(name, songList)
    if not rep_ids:
        return 2, None
    for song_id in rep_ids.copy():
        song_info = find_song_by_id(song_id, songList)
        if not song_info:
            rep_ids.remove(song_id)
            continue

        id_int = int(song_id)
        if music_type:
            if music_type.casefold() == "dx":
                if song_info["type"] != "DX":
                    rep_ids.remove(song_id)
            elif (
                music_type.casefold() == "sd"
                or music_type == "标准"
                or music_type == "标"
            ):
                if song_info["type"] != "SD":
                    rep_ids.remove(song_id)
        elif song_info["type"] != "DX" or str(id_int % 10000) not in rep_ids:
            other_id = str(id_int + 10000)
            if other_id in rep_ids:
                continue
            other_info = find_song_by_id(other_id, songList)
            if other_info:
                rep_ids.append(other_id)
    if not rep_ids:
        return 2, None
    elif len(rep_ids) > 20:
        return 3, rep_ids
    elif len(rep_ids) > 1:
        output_lst = set()
        for song_id in sorted(rep_ids, key=int):
            song_info = find_song_by_id(song_id, songList)
            song_title = song_info["title"]
            output_lst.add(song_title)

        return 1, output_lst if len(output_lst) > 1 else song_info

    song_info = find_song_by_id(rep_ids[0], songList)
    if not song_info:
        return 2, None

    return 0, song_info


@best50.handle()
async def _(event: MessageEvent):
    target_qq = event.get_user_id()
    for message in event.get_message():
        if message.type != "at":
            continue
        target_qq = message.data["qq"]
        if target_qq == event.get_user_id():
            continue
        with shelve.open("./data/user_config.db") as config:
            if (
                target_qq not in config
                or "allow_other" not in config[target_qq]
                or config[target_qq]["allow_other"]
            ):
                break
    else:
        if target_qq != event.get_user_id():
            msg = (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("他不允许其他人查询他的成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/3.png")),
            )
            await best50.finish(msg)
    data, status = await get_player_data(target_qq)
    if status == 400:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text(
                f"迪拉熊没有找到{"你" if target_qq == event.get_user_id() else "他"}的信息"
            ),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await best50.finish(msg)
    elif status == 403:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text(
                f"{"你" if target_qq == event.get_user_id() else "他"}在查分器启用了隐私或者没有同意查分器的用户协议"
            ),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await best50.finish(msg)
    elif not data:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("（查分器出了点问题）"),
            MessageSegment.image(Path("./Static/maimai/-1.png")),
        )
        await best50.finish(msg)
    songList = await get_music_data()
    charts = data["charts"]
    b35, b15 = sorted(
        charts["sd"], key=lambda x: (x["ra"], x["ds"], x["achievements"]), reverse=True
    ), sorted(
        charts["dx"], key=lambda x: (x["ra"], x["ds"], x["achievements"]), reverse=True
    )
    if not b35 and not b15:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text(
                f"{"你" if target_qq == event.get_user_id() else "他"}没有上传任何成绩"
            ),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await best50.finish(msg)
    await best50.send(
        (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    nickname = data["nickname"]
    dani = data["additional_rating"]
    img = await generateb50(
        b35=b35,
        b15=b15,
        nickname=nickname,
        qq=target_qq,
        dani=dani,
        type="b50",
        songList=songList,
    )
    msg = (MessageSegment.at(event.user_id), MessageSegment.image(img))
    await best50.send(msg)


@ap50.handle()
async def _(event: MessageEvent):
    target_qq = event.get_user_id()
    for message in event.get_message():
        if message.type != "at":
            continue
        target_qq = message.data["qq"]
        if target_qq == event.get_user_id():
            continue
        with shelve.open("./data/user_config.db") as config:
            if (
                target_qq not in config
                or "allow_other" not in config[target_qq]
                or config[target_qq]["allow_other"]
            ):
                break
    else:
        if target_qq != event.get_user_id():
            msg = (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("他不允许其他人查询他的成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/3.png")),
            )
            await ap50.finish(msg)
    data, status = await get_player_records(target_qq)
    if status == 400:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text(
                f"迪拉熊没有找到{"你" if target_qq == event.get_user_id() else "他"}的信息"
            ),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await ap50.finish(msg)
    elif not data:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("（查分器出了点问题）"),
            MessageSegment.image(Path("./Static/maimai/-1.png")),
        )
        await ap50.finish(msg)
    records = data["records"]
    if not records:
        await ap50.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text(
                    f"{"你" if target_qq == event.get_user_id() else "他"}没有上传任何成绩"
                ),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    songList = await get_music_data()
    ap35, ap15, _ = await records_to_b50(records, songList, ["ap", "app"])
    if not ap35 and not ap15:
        await ap50.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text(
                    f"{"你" if target_qq == event.get_user_id() else "他"}没有全完美的成绩"
                ),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    await ap50.send(
        (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    nickname = data["nickname"]
    dani = data["additional_rating"]
    img = await generateb50(
        b35=ap35,
        b15=ap15,
        nickname=nickname,
        qq=target_qq,
        dani=dani,
        type="ap50",
        songList=songList,
    )
    msg = (MessageSegment.at(event.user_id), MessageSegment.image(img))
    await ap50.send(msg)


@fc50.handle()
async def _(event: MessageEvent):
    target_qq = event.get_user_id()
    for message in event.get_message():
        if message.type != "at":
            continue
        target_qq = message.data["qq"]
        if target_qq == event.get_user_id():
            continue
        with shelve.open("./data/user_config.db") as config:
            if (
                target_qq not in config
                or "allow_other" not in config[target_qq]
                or config[target_qq]["allow_other"]
            ):
                break
    else:
        if target_qq != event.get_user_id():
            msg = (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("他不允许其他人查询他的成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/3.png")),
            )
            await fc50.finish(msg)
    data, status = await get_player_records(target_qq)
    if status == 400:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text(
                f"迪拉熊没有找到{"你" if target_qq == event.get_user_id() else "他"}的信息"
            ),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await fc50.finish(msg)
    elif not data:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("（查分器出了点问题）"),
            MessageSegment.image(Path("./Static/maimai/-1.png")),
        )
        await fc50.finish(msg)
    records = data["records"]
    if not records:
        await fc50.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text(
                    f"{"你" if target_qq == event.get_user_id() else "他"}没有上传任何成绩"
                ),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    songList = await get_music_data()
    fc35, fc15, _ = await records_to_b50(records, songList, ["fc", "fcp"])
    if not fc35 and not fc15:
        await fc50.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text(
                    f"{"你" if target_qq == event.get_user_id() else "他"}没有全连的成绩"
                ),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    await fc50.send(
        (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    nickname = data["nickname"]
    dani = data["additional_rating"]
    img = await generateb50(
        b35=fc35,
        b15=fc15,
        nickname=nickname,
        qq=target_qq,
        dani=dani,
        type="fc50",
        songList=songList,
    )
    msg = (MessageSegment.at(event.user_id), MessageSegment.image(img))
    await fc50.send(msg)


@fit50.handle()
async def _(event: MessageEvent):
    target_qq = event.get_user_id()
    for message in event.get_message():
        if message.type != "at":
            continue
        target_qq = message.data["qq"]
        if target_qq == event.get_user_id():
            continue
        with shelve.open("./data/user_config.db") as config:
            if (
                target_qq not in config
                or "allow_other" not in config[target_qq]
                or config[target_qq]["allow_other"]
            ):
                break
    else:
        if target_qq != event.get_user_id():
            msg = (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("他不允许其他人查询他的成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/3.png")),
            )
            await fit50.finish(msg)
    data, status = await get_player_records(target_qq)
    if status == 400:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text(
                f"迪拉熊没有找到{"你" if target_qq == event.get_user_id() else "他"}的信息"
            ),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await fit50.finish(msg)
    elif not data:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("（查分器出了点问题）"),
            MessageSegment.image(Path("./Static/maimai/-1.png")),
        )
        await fit50.finish(msg)
    records = data["records"]
    if not records:
        await fit50.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text(
                    f"{"你" if target_qq == event.get_user_id() else "他"}没有上传任何成绩"
                ),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    songList = await get_music_data()
    b35, b15, mask_enabled = await records_to_b50(records, songList, is_fit=True)
    if not b35 and not b15:
        if mask_enabled:
            msg = f"迪拉熊无法获取{"你" if target_qq == event.get_user_id() else "他"}的真实成绩"
        else:
            msg = f"{"你" if target_qq == event.get_user_id() else "他"}没有上传任何匹配的成绩"
        await fit50.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text(msg),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    await fit50.send(
        (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    nickname = data["nickname"]
    dani = data["additional_rating"]
    img = await generateb50(
        b35=b35,
        b15=b15,
        nickname=nickname,
        qq=target_qq,
        dani=dani,
        type="fit50",
        songList=songList,
    )
    msg = (MessageSegment.at(event.user_id), MessageSegment.image(img))
    await fit50.send(msg)


@rate50.handle()
async def _(event: MessageEvent):
    target_qq = event.get_user_id()
    for message in event.get_message():
        if message.type != "at":
            continue
        target_qq = message.data["qq"]
        if target_qq == event.get_user_id():
            continue
        with shelve.open("./data/user_config.db") as config:
            if (
                target_qq not in config
                or "allow_other" not in config[target_qq]
                or config[target_qq]["allow_other"]
            ):
                break
    else:
        if target_qq != event.get_user_id():
            msg = (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("他不允许其他人查询他的成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/3.png")),
            )
            await rate50.finish(msg)
    data, status = await get_player_records(target_qq)
    if status == 400:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text(
                f"迪拉熊没有找到{"你" if target_qq == event.get_user_id() else "他"}的信息"
            ),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await rate50.finish(msg)
    elif not data:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("（查分器出了点问题）"),
            MessageSegment.image(Path("./Static/maimai/-1.png")),
        )
        await rate50.finish(msg)
    records = data["records"]
    if not records:
        await rate50.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text(
                    f"{"你" if target_qq == event.get_user_id() else "他"}没有上传任何成绩"
                ),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    msg_text = event.get_plaintext().replace("+", "p").casefold()
    rate_rules = re.findall(r"s{1,3}p?|a{1,3}|b{1,3}|[cd]", msg_text, re.I)
    songList = await get_music_data()
    rate35, rate15, _ = await records_to_b50(records, songList, rate_rules=rate_rules)
    if not rate35 and not rate15:
        await rate50.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text(
                    f"{"你" if target_qq == event.get_user_id() else "他"}没有上传任何匹配的成绩"
                ),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    await rate50.send(
        (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    nickname = data["nickname"]
    dani = data["additional_rating"]
    img = await generateb50(
        b35=rate35,
        b15=rate15,
        nickname=nickname,
        qq=target_qq,
        dani=dani,
        type="rate50",
        songList=songList,
    )
    msg = (MessageSegment.at(event.user_id), MessageSegment.image(img))
    await rate50.send(msg)


@dxs50.handle()
async def _(event: MessageEvent):
    target_qq = event.get_user_id()
    for message in event.get_message():
        if message.type != "at":
            continue
        target_qq = message.data["qq"]
        if target_qq == event.get_user_id():
            continue
        with shelve.open("./data/user_config.db") as config:
            if (
                target_qq not in config
                or "allow_other" not in config[target_qq]
                or config[target_qq]["allow_other"]
            ):
                break
    else:
        if target_qq != event.get_user_id():
            msg = (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("他不允许其他人查询他的成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/3.png")),
            )
            await dxs50.finish(msg)
    data, status = await get_player_records(target_qq)
    if status == 400:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text(
                f"迪拉熊没有找到{"你" if target_qq == event.get_user_id() else "他"}的信息"
            ),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await dxs50.finish(msg)
    elif not data:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("（查分器出了点问题）"),
            MessageSegment.image(Path("./Static/maimai/-1.png")),
        )
        await dxs50.finish(msg)
    records = data["records"]
    if not records:
        await dxs50.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text(
                    f"{"你" if target_qq == event.get_user_id() else "他"}没有上传任何成绩"
                ),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    songList = await get_music_data()
    dxs35, dxs15, mask_enabled = await records_to_b50(records, songList, is_dxs=True)
    if not dxs35 and not dxs15:
        if mask_enabled:
            msg = f"迪拉熊无法获取{"你" if target_qq == event.get_user_id() else "他"}的真实成绩"
        else:
            msg = f"{"你" if target_qq == event.get_user_id() else "他"}没有上传任何匹配的成绩"
        await dxs50.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text(msg),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    await dxs50.send(
        (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    nickname = data["nickname"]
    dani = data["additional_rating"]
    img = await generateb50(
        b35=dxs35,
        b15=dxs15,
        nickname=nickname,
        qq=target_qq,
        dani=dani,
        type="dxs50",
        songList=songList,
    )
    msg = (MessageSegment.at(event.user_id), MessageSegment.image(img))
    await dxs50.send(msg)


@star50.handle()
async def _(event: MessageEvent):
    target_qq = event.get_user_id()
    for message in event.get_message():
        if message.type != "at":
            continue
        target_qq = message.data["qq"]
        if target_qq == event.get_user_id():
            continue
        with shelve.open("./data/user_config.db") as config:
            if (
                target_qq not in config
                or "allow_other" not in config[target_qq]
                or config[target_qq]["allow_other"]
            ):
                break
    else:
        if target_qq != event.get_user_id():
            msg = (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("他不允许其他人查询他的成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/3.png")),
            )
            await star50.finish(msg)
    data, status = await get_player_records(target_qq)
    if status == 400:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text(
                f"迪拉熊没有找到{"你" if target_qq == event.get_user_id() else "他"}的信息"
            ),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await star50.finish(msg)
    elif not data:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("（查分器出了点问题）"),
            MessageSegment.image(Path("./Static/maimai/-1.png")),
        )
        await star50.finish(msg)
    records = data["records"]
    if not records:
        await star50.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text(
                    f"{"你" if target_qq == event.get_user_id() else "他"}没有上传任何成绩"
                ),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    songList = await get_music_data()
    find = re.fullmatch(r"dlxx50((?:\s*[1-5])+)", event.get_plaintext(), re.I)
    star35, star15, mask_enabled = await records_to_b50(
        records, songList, is_dxs=True, dx_star_count=find.group(1)
    )
    if not star35 and not star15:
        if mask_enabled:
            msg = f"迪拉熊无法获取{"你" if target_qq == event.get_user_id() else "他"}的真实成绩"
        else:
            msg = f"{"你" if target_qq == event.get_user_id() else "他"}没有上传任何匹配的成绩"
        await star50.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text(msg),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    await star50.send(
        (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    nickname = data["nickname"]
    dani = data["additional_rating"]
    img = await generateb50(
        b35=star35,
        b15=star15,
        nickname=nickname,
        qq=target_qq,
        dani=dani,
        type="star50",
        songList=songList,
    )
    msg = (MessageSegment.at(event.user_id), MessageSegment.image(img))
    await star50.send(msg)


@cf50.handle()
async def _(event: MessageEvent):
    sender_qq = event.get_user_id()
    for message in event.get_message():
        if message.type != "at":
            continue
        target_qq = message.data["qq"]
        if target_qq == sender_qq:
            continue
        with shelve.open("./data/user_config.db") as config:
            if (
                target_qq not in config
                or "allow_other" not in config[target_qq]
                or config[target_qq]["allow_other"]
            ):
                break
    else:
        if target_qq != sender_qq:
            msg = (
                MessageSegment.at(sender_qq),
                MessageSegment.text(" "),
                MessageSegment.text("他不允许其他人查询他的成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/3.png")),
            )
            await cf50.finish(msg)
    if target_qq == sender_qq:
        msg = (
            MessageSegment.at(sender_qq),
            MessageSegment.text(" "),
            MessageSegment.text("你不可以和自己比较"),
            MessageSegment.image(Path("./Static/Maimai/Function/3.png")),
        )
        await cf50.finish(msg)
    sender_data, status = await get_player_records(sender_qq)
    if status == 400:
        msg = (
            MessageSegment.at(sender_qq),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊没有找到你的信息"),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await cf50.finish(msg)
    elif status == 403:
        msg = (
            MessageSegment.at(sender_qq),
            MessageSegment.text(" "),
            MessageSegment.text("你在查分器启用了隐私或者没有同意查分器的用户协议"),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await cf50.finish(msg)
    elif not sender_data:
        msg = (
            MessageSegment.at(sender_qq),
            MessageSegment.text(" "),
            MessageSegment.text("（查分器出了点问题）"),
            MessageSegment.image(Path("./Static/maimai/-1.png")),
        )
        await cf50.finish(msg)
    target_data, status = await get_player_records(target_qq)
    if status == 400:
        msg = (
            MessageSegment.at(sender_qq),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊没有找到他的信息"),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await cf50.finish(msg)
    elif status == 403:
        msg = (
            MessageSegment.at(sender_qq),
            MessageSegment.text(" "),
            MessageSegment.text("他在查分器启用了隐私或者没有同意查分器的用户协议"),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await cf50.finish(msg)
    elif not target_data:
        msg = (
            MessageSegment.at(sender_qq),
            MessageSegment.text(" "),
            MessageSegment.text("（查分器出了点问题）"),
            MessageSegment.image(Path("./Static/maimai/-1.png")),
        )
        await cf50.finish(msg)
    songList = await get_music_data()
    sender_records = sender_data["records"]
    if not sender_records:
        await cf50.finish(
            (
                MessageSegment.at(sender_qq),
                MessageSegment.text(" "),
                MessageSegment.text("你没有上传任何成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    target_records = target_data["records"]
    if not target_records:
        await cf50.finish(
            (
                MessageSegment.at(sender_qq),
                MessageSegment.text(" "),
                MessageSegment.text("他没有上传任何成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    songList = await get_music_data()
    b35, b15, mask_enabled = await compare_b50(sender_records, target_records, songList)
    if not b35 and not b15:
        if mask_enabled:
            msg = "迪拉熊无法获取真实成绩"
        else:
            msg = "没有上传任何匹配的成绩"
        await cf50.finish(
            (
                MessageSegment.at(sender_qq),
                MessageSegment.text(" "),
                MessageSegment.text(msg),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    await cf50.send(
        (
            MessageSegment.at(sender_qq),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    nickname = target_data["nickname"]
    dani = target_data["additional_rating"]
    img = await generateb50(
        b35=b35,
        b15=b15,
        nickname=nickname,
        qq=target_qq,
        dani=dani,
        type="cf50",
        songList=songList,
    )
    msg = (MessageSegment.at(sender_qq), MessageSegment.image(img))
    await cf50.send(msg)


@sd50.handle()
async def _(event: MessageEvent):
    target_qq = event.get_user_id()
    for message in event.get_message():
        if message.type != "at":
            continue
        target_qq = message.data["qq"]
        if target_qq == event.get_user_id():
            continue
        with shelve.open("./data/user_config.db") as config:
            if (
                target_qq not in config
                or "allow_other" not in config[target_qq]
                or config[target_qq]["allow_other"]
            ):
                break
    else:
        if target_qq != event.get_user_id():
            msg = (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("他不允许其他人查询他的成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/3.png")),
            )
            await sd50.finish(msg)
    data, status = await get_player_records(target_qq)
    if status == 400:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text(
                f"迪拉熊没有找到{"你" if target_qq == event.get_user_id() else "他"}的信息"
            ),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await sd50.finish(msg)
    elif not data:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("（查分器出了点问题）"),
            MessageSegment.image(Path("./Static/maimai/-1.png")),
        )
        await sd50.finish(msg)
    records = data["records"]
    if not records:
        await sd50.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text(
                    f"{"你" if target_qq == event.get_user_id() else "他"}没有上传任何成绩"
                ),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    songList = await get_music_data()
    b35, b15, mask_enabled = await records_to_b50(records, songList, is_sd=True)
    if not b35 and not b15:
        if mask_enabled:
            msg = f"迪拉熊无法获取{"你" if target_qq == event.get_user_id() else "他"}的真实成绩"
        else:
            msg = f"{"你" if target_qq == event.get_user_id() else "他"}没有上传任何匹配的成绩"
        await sd50.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text(msg),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    await sd50.send(
        (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    nickname = data["nickname"]
    dani = data["additional_rating"]
    img = await generateb50(
        b35=b35,
        b15=b15,
        nickname=nickname,
        qq=target_qq,
        dani=dani,
        type="sd50",
        songList=songList,
    )
    msg = (MessageSegment.at(event.user_id), MessageSegment.image(img))
    await sd50.send(msg)


@all50.handle()
async def _(event: MessageEvent):
    target_qq = event.get_user_id()
    for message in event.get_message():
        if message.type != "at":
            continue
        target_qq = message.data["qq"]
        if target_qq == event.get_user_id():
            continue
        with shelve.open("./data/user_config.db") as config:
            if (
                target_qq not in config
                or "allow_other" not in config[target_qq]
                or config[target_qq]["allow_other"]
            ):
                break
    else:
        if target_qq != event.get_user_id():
            msg = (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("他不允许其他人查询他的成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/3.png")),
            )
            await all50.finish(msg)
    data, status = await get_player_records(target_qq)
    if status == 400:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text(
                f"迪拉熊没有找到{"你" if target_qq == event.get_user_id() else "他"}的信息"
            ),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await all50.finish(msg)
    elif not data:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("（查分器出了点问题）"),
            MessageSegment.image(Path("./Static/maimai/-1.png")),
        )
        await all50.finish(msg)
    records = data["records"]
    if not records:
        await all50.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text(
                    f"{"你" if target_qq == event.get_user_id() else "他"}没有上传任何成绩"
                ),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    songList = await get_music_data()
    all35, all15, _ = await records_to_b50(records, songList, is_all=True)
    await all50.send(
        (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    nickname = data["nickname"]
    dani = data["additional_rating"]
    img = await generateb50(
        b35=all35,
        b15=all15,
        nickname=nickname,
        qq=target_qq,
        dani=dani,
        type="all50",
        songList=songList,
    )
    msg = (MessageSegment.at(event.user_id), MessageSegment.image(img))
    await all50.send(msg)


@rr50.handle()
async def _(event: MessageEvent):
    match = re.fullmatch(r"dlxrr(?:50)?\s*(\d+)", event.get_plaintext(), re.I)
    rating = 0
    if match:
        rating = int(match.group(1))
        if rating < 0:
            await rr50.send(
                (
                    MessageSegment.at(event.user_id),
                    MessageSegment.text(" "),
                    MessageSegment.text("没有任何匹配的成绩"),
                    MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
                )
            )
            return

    songList = await get_music_data()
    rr35, rr15, _ = await records_to_b50(
        None,
        songList,
        rating=rating,
    )
    if not rr35 and not rr15:
        await rr50.send(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("没有任何匹配的成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
        return

    await rr50.send(
        (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    nickname = "ＡＡＡＡＡＡＡＡ"
    dani = 22
    img = await generateb50(
        b35=rr35,
        b15=rr15,
        nickname=nickname,
        qq="0",
        dani=dani,
        type="rr50",
        songList=songList,
    )
    msg = (MessageSegment.at(event.user_id), MessageSegment.image(img))
    await rr50.send(msg)


@sunlist.handle()
async def _(event: MessageEvent):
    qq = event.get_user_id()
    data, status = await get_player_records(qq)
    if status == 400:
        msg = (
            MessageSegment.at(qq),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊没有找到你的信息"),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await sunlist.finish(msg)
    elif not data:
        msg = (
            MessageSegment.at(qq),
            MessageSegment.text(" "),
            MessageSegment.text("（查分器出了点问题）"),
            MessageSegment.image(Path("./Static/maimai/-1.png")),
        )
        await sunlist.finish(msg)
    records = data["records"]
    if not records:
        await sunlist.finish(
            (
                MessageSegment.at(qq),
                MessageSegment.text(" "),
                MessageSegment.text("你没有上传任何成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    songList = await get_music_data()
    filted_records, mask_enabled = records_filter(
        records=records, is_sun=True, songList=songList
    )
    if not filted_records:
        if mask_enabled:
            msg = "迪拉熊无法获取你的真实成绩"
        else:
            msg = "你没有上传任何匹配的成绩"
        await sunlist.finish(
            (
                MessageSegment.at(qq),
                MessageSegment.text(" "),
                MessageSegment.text(msg),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    msg = event.get_plaintext()
    pattern = r"\d+"
    match = re.search(pattern, msg)
    if match:
        page = int(match.group())
        if page <= 0:
            page = 1
    else:
        page = 1
    all_page_num = math.ceil(len(filted_records) / 55)
    page = min(page, all_page_num)
    await sunlist.send(
        (
            MessageSegment.at(qq),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    input_records = get_page_records(filted_records, page=page)
    nickname = data["nickname"]
    rating = data["rating"]
    dani = data["additional_rating"]
    img = await generate_wcb(
        qq=qq,
        page=page,
        nickname=nickname,
        dani=dani,
        rating=rating,
        input_records=input_records,
        all_page_num=all_page_num,
        songList=songList,
    )
    msg = (MessageSegment.at(qq), MessageSegment.image(img))
    await sunlist.send(msg)


@locklist.handle()
async def _(event: MessageEvent):
    qq = event.get_user_id()
    data, status = await get_player_records(qq)
    if status == 400:
        msg = (
            MessageSegment.at(qq),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊没有找到你的信息"),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await locklist.finish(msg)
    elif not data:
        msg = (
            MessageSegment.at(qq),
            MessageSegment.text(" "),
            MessageSegment.text("（查分器出了点问题）"),
            MessageSegment.image(Path("./Static/maimai/-1.png")),
        )
        await locklist.finish(msg)
    records = data["records"]
    if not records:
        await locklist.finish(
            (
                MessageSegment.at(qq),
                MessageSegment.text(" "),
                MessageSegment.text("你没有上传任何成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    songList = await get_music_data()
    filted_records, mask_enabled = records_filter(
        records=records, is_lock=True, songList=songList
    )
    if not filted_records:
        if mask_enabled:
            msg = "迪拉熊无法获取你的真实成绩"
        else:
            msg = "你没有上传任何匹配的成绩"
        await locklist.finish(
            (
                MessageSegment.at(qq),
                MessageSegment.text(" "),
                MessageSegment.text(msg),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    msg = event.get_plaintext()
    pattern = r"\d+"
    match = re.search(pattern, msg)
    if match:
        page = int(match.group())
        if page <= 0:
            page = 1
    else:
        page = 1
    all_page_num = math.ceil(len(filted_records) / 55)
    page = min(page, all_page_num)
    await locklist.send(
        (
            MessageSegment.at(qq),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    input_records = get_page_records(filted_records, page=page)
    nickname = data["nickname"]
    rating = data["rating"]
    dani = data["additional_rating"]
    img = await generate_wcb(
        qq=qq,
        page=page,
        nickname=nickname,
        dani=dani,
        rating=rating,
        input_records=input_records,
        all_page_num=all_page_num,
        songList=songList,
    )
    msg = (MessageSegment.at(qq), MessageSegment.image(img))
    await locklist.send(msg)


@wcb.handle()
async def _(event: MessageEvent):
    qq = event.get_user_id()
    msg = event.get_plaintext()
    pattern = r"(?:((?:\d+)(?:\.\d|\+)?)|(真|超|檄|橙|晓|桃|樱|紫|堇|白|雪|辉|舞|熊|华|爽|煌|宙|星|祭|祝|双))(?:\s*(\d+))?"
    match = re.search(pattern, msg)
    data, status = await get_player_records(qq)
    if status == 400:
        msg = (
            MessageSegment.at(qq),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊没有找到你的信息"),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await wcb.finish(msg)
    elif not data:
        msg = (
            MessageSegment.at(qq),
            MessageSegment.text(" "),
            MessageSegment.text("（查分器出了点问题）"),
            MessageSegment.image(Path("./Static/maimai/-1.png")),
        )
        await wcb.finish(msg)
    records = data["records"]
    if not records:
        await wcb.finish(
            (
                MessageSegment.at(qq),
                MessageSegment.text(" "),
                MessageSegment.text("你没有上传任何成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    songList = await get_music_data()
    level = match.group(1)
    if level and "." in level:
        ds = float(level)
        level = None
    else:
        ds = None
    gen = match.group(2)
    filted_records, _ = records_filter(
        records=records, level=level, ds=ds, gen=gen, songList=songList
    )
    if len(filted_records) == 0:
        await wcb.finish(
            (
                MessageSegment.at(qq),
                MessageSegment.text(" "),
                MessageSegment.text("你没有上传任何匹配的成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )

    if match.group(3):
        page = int(match.group(3))
        if page <= 0:
            page = 1
    else:
        page = 1
    all_page_num = math.ceil(len(filted_records) / 55)
    page = min(page, all_page_num)
    await wcb.send(
        (
            MessageSegment.at(qq),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    input_records = get_page_records(filted_records, page=page)
    rate_count = compute_record(records=filted_records)
    nickname = data["nickname"]
    rating = data["rating"]
    dani = data["additional_rating"]
    img = await generate_wcb(
        qq=qq,
        level=level,
        ds=ds,
        gen=gen,
        page=page,
        nickname=nickname,
        dani=dani,
        rating=rating,
        input_records=input_records,
        rate_count=rate_count,
        all_page_num=all_page_num,
        songList=songList,
    )
    msg = (MessageSegment.at(qq), MessageSegment.image(img))
    await wcb.send(msg)


@songinfo.handle()
async def _(event: MessageEvent):
    msg = event.get_plaintext()
    match = re.fullmatch(r"(?:chart|id)\s*(?:(dx|sd|标准?)\s*)?(.+)", msg, re.I)
    if not match:
        return

    music_type = match.group(1)
    song = match.group(2)
    if not song:
        return

    songList = await get_music_data()
    result, song_info = await get_info_by_name(song, music_type, songList)
    if result == 1:
        if isinstance(song_info, set):
            msg = f"迪拉熊找到啦~结果有：\r\n{"\r\n".join(song_info)}"
            await songinfo.finish(MessageSegment.text(msg))
    elif result == 2:
        await songinfo.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("迪拉熊没有找到匹配的乐曲"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    elif result == 3:
        await songinfo.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("结果太多啦，缩小范围再试试吧~"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    await songinfo.send(
        (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    if song_info["basic_info"]["genre"] == "宴会場":
        img = await utage_music_info(song_data=song_info)
    else:
        img = await music_info(song_data=song_info)
    msg = MessageSegment.image(img)
    await songinfo.send(msg)


@playinfo.handle()
async def _(event: MessageEvent):
    qq = event.get_user_id()
    msg = event.get_plaintext()
    match = re.fullmatch(r"(?:score|info)\s*(?:(dx|sd|标准?)\s*)?(.+)", msg, re.I)
    if not match:
        return

    music_type = match.group(1)
    song = match.group(2)
    if not song:
        return

    songList = await get_music_data()
    result, song_info = await get_info_by_name(song, music_type, songList)
    if result == 1:
        if isinstance(song_info, set):
            msg = f"迪拉熊找到啦~结果有：\r\n{"\r\n".join(song_info)}"
            await playinfo.finish(MessageSegment.text(msg))
    elif result == 2:
        await playinfo.finish(
            (
                MessageSegment.at(qq),
                MessageSegment.text(" "),
                MessageSegment.text("迪拉熊没有找到匹配的乐曲"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    elif result == 3:
        await playinfo.finish(
            (
                MessageSegment.at(qq),
                MessageSegment.text(" "),
                MessageSegment.text("结果太多啦，缩小范围再试试吧~"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    data, status = await get_player_record(qq, song_info["id"])
    if status == 400:
        msg = (
            MessageSegment.at(qq),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊没有找到你的信息"),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
        await playinfo.finish(msg)
    if status == 200:
        if not data:
            msg = (
                MessageSegment.at(qq),
                MessageSegment.text(" "),
                MessageSegment.text("迪拉熊没有找到匹配的乐曲"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
            await playinfo.finish(msg)
        records = data[song_info["id"]]
        if not records:
            msg = (
                MessageSegment.at(qq),
                MessageSegment.text(" "),
                MessageSegment.text("迪拉熊没有找到你在这首乐曲上的成绩"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
            await playinfo.finish(msg)
    elif not data:
        msg = (
            MessageSegment.at(qq),
            MessageSegment.text(" "),
            MessageSegment.text("（查分器出了点问题）"),
            MessageSegment.image(Path("./Static/maimai/-1.png")),
        )
        await playinfo.finish(msg)
    await playinfo.send(
        (
            MessageSegment.at(qq),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    img = await play_info(data, song_info)
    msg = MessageSegment.image(img)
    await playinfo.send((MessageSegment.at(qq), msg))


@scoreinfo.handle()
async def _(event: MessageEvent):
    msg = event.get_plaintext()
    pattern = r"(绿|黄|红|紫|白)\s*(?:(dx|sd|标准?)\s*)?(.+)"
    match = re.search(pattern, msg, re.I)
    type_index = ["绿", "黄", "红", "紫", "白"].index(match.group(1))
    music_type = match.group(2)
    song = match.group(3)
    if not song:
        return

    songList = await get_music_data()
    result, song_info = await get_info_by_name(song, music_type, songList)
    if result == 1:
        if isinstance(song_info, set):
            msg = f"迪拉熊找到啦~结果有：\r\n{"\r\n".join(song_info)}"
            await scoreinfo.finish(MessageSegment.text(msg))
    elif (
        result == 2
        or song_info["basic_info"]["genre"] == "宴会場"
        or len(song_info["level"]) <= type_index
    ):
        await scoreinfo.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("迪拉熊没有找到匹配的乐曲"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    elif result == 3:
        await scoreinfo.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("结果太多啦，缩小范围再试试吧~"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    await scoreinfo.send(
        (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )
    )
    img = await score_info(song_data=song_info, index=type_index)
    msg = MessageSegment.image(img)
    await scoreinfo.send(msg)


@playaudio.handle()
async def _(event: MessageEvent):
    msg = event.get_plaintext()
    match = re.fullmatch(r"dlx点歌\s*(.+)", msg, re.I)
    if not match:
        return

    song = match.group(1)
    if not song:
        return

    songList = await get_music_data()
    result, song_info = await get_info_by_name(song, None, songList)
    if result == 1:
        if isinstance(song_info, set):
            msg = f"迪拉熊找到啦~结果有：\r\n{"\r\n".join(song_info)}"
            await playaudio.finish(MessageSegment.text(msg))
    elif result == 2:
        await playaudio.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("迪拉熊没有找到匹配的乐曲"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    elif result == 3:
        await playaudio.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("结果太多啦，缩小范围再试试吧~"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    songname = song_info["title"]
    await playaudio.send(
        MessageSegment.text(f"迪拉熊正在准备播放{songname}，稍等一下mai~")
    )
    music_path = f"./Cache/Music/{int(song_info["id"]) % 10000}.mp3"
    if not os.path.exists(music_path):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://assets2.lxns.net/maimai/music/{int(song_info["id"]) % 10000}.mp3"
            ) as resp:
                with open(music_path, "wb") as fd:
                    async for chunk in resp.content.iter_chunked(1024):
                        fd.write(chunk)
    await playaudio.send(MessageSegment.record(music_path))


@randomsong.handle()
async def _(event: MessageEvent):
    msg = event.get_plaintext()
    pattern = r"(绿|黄|红|紫|白)?\s*((?:\d+)(?:\.\d|\+)?)"
    match = re.search(pattern, msg)
    level_label = match.group(1)
    if level_label:
        level_index = ["绿", "黄", "红", "紫", "白"].index(level_label)
    else:
        level_index = None
    level = match.group(2)
    s_type = "level"
    if "." in level:
        s_type = "ds"
    s_songs = list()
    songList = await get_music_data()
    for song in songList:
        s_list = song[s_type]
        if s_type == "ds":
            level = float(level)
        if level_index:
            if len(s_list) > level_index:
                if level == s_list[level_index]:
                    s_songs.append(song)
        elif level in s_list:
            s_songs.append(song)
    if len(s_songs) == 0:
        msg = "迪拉熊没有找到匹配的乐曲"
        await randomsong.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text(msg),
            )
        )
    song = random.choice(s_songs)
    await randomsong.send(
        (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )  # 绘制中
    )
    if song["basic_info"]["genre"] == "宴会場":
        img = await utage_music_info(song_data=song)
    else:
        img = await music_info(song_data=song)
    msg = MessageSegment.image(img)
    await randomsong.send((MessageSegment.at(event.user_id), msg))


@maiwhat.handle()
async def _(event: MessageEvent):
    songList = await get_music_data()
    song = random.choice(songList)
    await maiwhat.send(
        (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )  # 绘制中
    )
    if song["basic_info"]["genre"] == "宴会場":
        img = await utage_music_info(song_data=song)
    else:
        img = await music_info(song_data=song)
    msg = MessageSegment.image(img)
    await maiwhat.send((MessageSegment.at(event.user_id), msg))


@whatSong.handle()
async def _(event: MessageEvent):
    msg = event.get_plaintext()
    match = re.fullmatch(
        r"(?:search|查歌)\s*(?:(dx|sd|标准?)\s*)?(.+)|(?:(dx|sd|标准?)\s*)?(.+)是什么歌？?",
        msg,
        re.I,
    )
    if not match:
        return

    name = match.group(1) or match.group(4)
    music_type = match.group(2) or match.group(3)
    if not name:
        await whatSong.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text("迪拉熊不知道哦~"),
                MessageSegment.image(Path("./Static/Maimai/Function/2.png")),
            )
        )

    songList = await get_music_data()
    result, song_info = await get_info_by_name(name, music_type, songList)
    if result == 1:
        if isinstance(song_info, set):
            msg = f"迪拉熊找到啦~结果有：\r\n{"\r\n".join(song_info)}"
            await whatSong.finish(MessageSegment.text(msg))
    elif result == 2:
        await whatSong.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("迪拉熊不知道哦~"),
                MessageSegment.image(Path("./Static/Maimai/Function/2.png")),
            )
        )
    elif result == 3:
        await whatSong.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("结果太多啦，缩小范围再试试吧~"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    await whatSong.send(
        (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊绘制中，稍等一下mai~"),
        )  # 绘制中
    )
    if song_info["basic_info"]["genre"] == "宴会場":
        img = await utage_music_info(song_data=song_info)
    else:
        img = await music_info(song_data=song_info)
    msg = MessageSegment.image(img)
    await whatSong.send(msg)


# 查看别名
@aliasSearch.handle()
async def _(event: MessageEvent):
    msg = event.get_plaintext()
    match = re.fullmatch(
        r"(?:alias|查看?别名)\s*(.+)|(.+)有(什么|哪些)别名？?", msg, re.I
    )
    if not match:
        return

    name = match.group(1) or match.group(2)
    if not name:
        await aliasSearch.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("迪拉熊不知道哦~"),
                MessageSegment.image(Path("./Static/Maimai/Function/2.png")),
            )
        )

    songList = await get_music_data()
    result, song_info = await get_info_by_name(name, None, songList)
    if result == 1:
        if isinstance(song_info, set):
            msg = f"迪拉熊找到啦~结果有：\r\n{"\r\n".join(song_info)}"
            await aliasSearch.finish(MessageSegment.text(msg))
    elif result == 2:
        await aliasSearch.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("迪拉熊不知道哦~"),
                MessageSegment.image(Path("./Static/Maimai/Function/2.png")),
            )
        )
    elif result == 3:
        await aliasSearch.finish(
            (
                MessageSegment.at(event.user_id),
                MessageSegment.text(" "),
                MessageSegment.text("结果太多啦，缩小范围再试试吧~"),
                MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
            )
        )
    song_id = int(song_info["id"]) - 10000
    alias = set()
    alias.add(song_info["id"])
    alias_list = await get_alias_list_lxns()
    for d in alias_list["aliases"]:
        if d["song_id"] == song_id:
            alias |= set(d["aliases"])
    alias_list = await get_alias_list_xray()
    for id, d in alias_list.items():
        if int(id) - 10000 == song_id:
            alias |= set(d)
    alias_list = await get_alias_list_ycn()
    for d in alias_list["content"]:
        if d["SongID"] - 10000 == song_id:
            alias |= set(d["Alias"])
    if not alias:
        msg = (
            MessageSegment.at(event.user_id),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊不知道哦~"),
            MessageSegment.image(Path("./Static/Maimai/Function/2.png")),
        )
    else:
        song_alias = "\r\n".join(sorted(alias))
        msg = f"迪拉熊找到啦~别名有：\r\n{song_alias}\r\n\r\n感谢落雪查分器、X-ray Bot及YuzuChaN Bot提供数据支持"
    await aliasSearch.send(MessageSegment.text(msg))


@all_frame.handle()
async def _():
    path = "./Static/maimai/allFrame.png"
    await all_frame.send(MessageSegment.image(Path(path)))


@all_plate.handle()
async def _():
    path = "./Static/maimai/allPlate.png"
    await all_plate.send(MessageSegment.image(Path(path)))


@set_plate.handle()
async def _(event: MessageEvent):
    qq = event.get_user_id()
    msg = event.get_plaintext()
    id = re.search(r"\d+", msg).group()
    plate_path = f"./Cache/Plate/{id}.png"
    if not os.path.exists(plate_path):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://assets2.lxns.net/maimai/plate/{int(id)}.png"
            ) as resp:
                if resp.status != 200:
                    msg = (
                        MessageSegment.at(qq),
                        MessageSegment.text(" "),
                        MessageSegment.text("迪拉熊没有找到合适的姓名框"),
                        MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
                    )
                    await set_plate.finish(msg)

                with open(plate_path, "wb") as fd:
                    async for chunk in resp.content.iter_chunked(1024):
                        fd.write(chunk)

    with shelve.open("./data/user_config.db") as config:
        if qq not in config:
            config.setdefault(qq, {"plate": id})
        else:
            cfg = config[qq]
            if "plate" not in config[qq]:
                cfg.setdefault("plate", id)
            else:
                cfg["plate"] = id
            config[qq] = cfg

    msg = "迪拉熊帮你换好啦~"
    await set_plate.send(
        (MessageSegment.at(qq), MessageSegment.text(" "), MessageSegment.text(msg))
    )


@set_frame.handle()
async def _(event: MessageEvent):
    qq = event.get_user_id()
    msg = event.get_plaintext()
    id = re.search(r"\d+", msg).group()
    dir_path = "./Static/maimai/Frame/"
    file_name = f"UI_Frame_{id}.png"
    file_path = Path(dir_path) / file_name
    if os.path.exists(file_path):
        with shelve.open("./data/user_config.db") as config:
            if qq not in config:
                config.setdefault(qq, {"frame": id})
            else:
                cfg = config[qq]
                if "frame" not in config[qq]:
                    cfg.setdefault("frame", id)
                else:
                    cfg["frame"] = id
                config[qq] = cfg

        msg = (
            MessageSegment.at(qq),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊帮你换好啦~"),
        )
    else:
        msg = (
            MessageSegment.at(qq),
            MessageSegment.text(" "),
            MessageSegment.text("迪拉熊没有找到合适的背景"),
            MessageSegment.image(Path("./Static/Maimai/Function/1.png")),
        )
    await set_frame.send(msg)


@ratj_on.handle()
async def _(event: MessageEvent):
    qq = event.get_user_id()
    with shelve.open("./data/user_config.db") as config:
        if qq not in config:
            config.setdefault(qq, {"rating_tj": True})
        else:
            cfg = config[qq]
            if "rating_tj" not in config[qq]:
                cfg.setdefault("rating_tj", True)
            else:
                cfg["rating_tj"] = True
            config[qq] = cfg

    msg = "迪拉熊帮你改好啦~"
    await ratj_on.send(
        (MessageSegment.at(qq), MessageSegment.text(" "), MessageSegment.text(msg))
    )


@ratj_off.handle()
async def _(event: MessageEvent):
    qq = event.get_user_id()
    with shelve.open("./data/user_config.db") as config:
        if qq not in config:
            config.setdefault(qq, {"rating_tj": False})
        else:
            cfg = config[qq]
            if "rating_tj" not in config[qq]:
                cfg.setdefault("rating_tj", False)
            else:
                cfg["rating_tj"] = False
            config[qq] = cfg

    msg = "迪拉熊帮你改好啦~"
    await ratj_off.send(
        (MessageSegment.at(qq), MessageSegment.text(" "), MessageSegment.text(msg))
    )


@allow_other_on.handle()
async def _(event: MessageEvent):
    qq = event.get_user_id()
    with shelve.open("./data/user_config.db") as config:
        if qq not in config:
            config.setdefault(qq, {"allow_other": True})
        else:
            cfg = config[qq]
            if "allow_other" not in config[qq]:
                cfg.setdefault("allow_other", True)
            else:
                cfg["allow_other"] = True
            config[qq] = cfg

    msg = "迪拉熊帮你改好啦~"
    await allow_other_on.send(
        (MessageSegment.at(qq), MessageSegment.text(" "), MessageSegment.text(msg))
    )


@allow_other_off.handle()
async def _(event: MessageEvent):
    qq = event.get_user_id()
    with shelve.open("./data/user_config.db") as config:
        if qq not in config:
            config.setdefault(qq, {"allow_other": False})
        else:
            cfg = config[qq]
            if "allow_other" not in config[qq]:
                cfg.setdefault("allow_other", False)
            else:
                cfg["allow_other"] = False
            config[qq] = cfg

    msg = "迪拉熊帮你改好啦~"
    await allow_other_off.send(
        (MessageSegment.at(qq), MessageSegment.text(" "), MessageSegment.text(msg))
    )
