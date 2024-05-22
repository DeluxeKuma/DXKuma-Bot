import asyncio
import datetime
import os
import random
import re
import shelve
import time
from pathlib import Path

import requests
from nonebot import on_regex, Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment

from util.Config import config


def is_admin(event: GroupMessageEvent):
    qq = event.user_id
    if qq in config.admin:
        return True

    return False


kuma_pic = on_regex(r'^((随机)(迪拉|滴蜡)熊|dlx)(涩图|色图|瑟图|st|)$')
rank = on_regex(r'^(迪拉熊排行榜|dlxlist)$')
upload = on_regex(r'^(upload)-(dlx|dlxst)', rule=is_admin)

KUMAPIC = './src/kuma-pic/normal'
KUMAPIC_R18 = './src/kuma-pic/r18'
DATA_PATH = './data/random_pic/count.db'


def get_time():
    today = datetime.date.today()

    # 获取当前年份
    year = today.year

    # 获取当前日期所在的周数
    week_number = today.isocalendar()[1]

    # 将年份和周数拼接成字符串
    result = str(year) + str(week_number)
    return result


async def update_count(qq: str, type: str):
    time = get_time()

    with shelve.open(DATA_PATH) as count_data:
        if qq not in count_data:
            count = count_data.setdefault(qq, {})
        else:
            count = count_data[qq]
        if time not in count:
            times = count.setdefault(time, {"kuma": 0, "kuma_r18": 0})
        else:
            times = count[time]

        times[type] += 1
        count_data[qq] = count


async def gen_rank(data, time):
    leaderboard = []

    for qq, qq_data in data.items():
        if time in qq_data:
            total_count = qq_data[time]["kuma"] + qq_data[time]["kuma_r18"]
            leaderboard.append((qq, total_count))

    leaderboard.sort(key=lambda x: x[1], reverse=True)

    return leaderboard[:5]


@kuma_pic.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    qq = event.get_user_id()
    msg = str(event.get_message())
    type = 'kuma'
    path = KUMAPIC
    if '涩图' in msg or '色图' in msg or '瑟图' in msg or 'st' in msg:
        type = 'kuma_r18'
        path = KUMAPIC_R18
    weight = random.randint(1, 100)
    if group_id == 967611986:  # 不被限制的 group_id
        pass
    elif type == 'kuma_r18' and group_id not in [
        236030263,
        938593095,
    ]:  # type 为 'kuma_r18' 且非指定 group_id
        msg = (
            MessageSegment.text('迪拉熊不准你看'),
            MessageSegment.image(Path('./src/notplay.png')),
        )
        await kuma_pic.finish(msg)
    else:
        if weight <= 10:
            if type == 'kuma':
                msg = MessageSegment.text('迪拉熊怕你沉溺其中，所以图就先不发了~')
            elif type == 'kuma_r18':
                msg = MessageSegment.text('迪拉熊关心你的身体健康，所以图就先不发了~')
            await kuma_pic.finish(msg)

    files = os.listdir(path)
    file = random.choice(files)
    pic_path = os.path.join(path, file)
    await update_count(qq=qq, type=type)
    send_msg = await kuma_pic.send(MessageSegment.image(Path(pic_path)))
    if type == 'kuma_r18':
        await asyncio.sleep(10)
        msg_id = send_msg['message_id']
        await bot.delete_msg(message_id=msg_id)


@rank.handle()
async def _(bot: Bot):
    time = get_time()

    with shelve.open(DATA_PATH) as count_data:
        leaderboard = await gen_rank(count_data, time)

    leaderboard_output = []
    count = min(len(leaderboard), 5)  # 最多显示5个人，取实际人数和5的较小值
    for i, (qq, total_count) in enumerate(leaderboard[:count], start=1):
        user_name = (await bot.get_stranger_info(user_id=int(qq), no_cache=False))[
            'nickname'
        ]
        rank_str = f"{i}. {user_name} - {total_count}"
        leaderboard_output.append(rank_str)

    msg = '\n'.join(leaderboard_output)
    msg = f'本周迪拉熊厨力最高的人是……\n{msg}\n迪拉熊给上面{count}个宝宝一个大大的拥抱~\n（积分每周一重算）'
    await rank.finish(msg)


@upload.handle()
async def _(event: GroupMessageEvent):
    text = str(event.get_message())
    urls = re.findall(r"url=([^&\]]+)", text)
    folder_path = KUMAPIC
    total = len(urls)
    count = 0
    if 'dlxst' in text:
        folder_path = KUMAPIC_R18
    for url in urls:
        count += 1
        try:
            response = requests.get(url)
            if response.status_code == 200:
                timestamp = str(int(time.time() * 1000))  # 获取当前时间戳
                file_name = timestamp + '.jpg'  # 以时间戳作为文件名
                file_path = os.path.join(folder_path, file_name)
                with open(file_path, 'wb') as file:
                    file.write(response.content)
                await upload.send(f"第{count}/{total}张图片上传完成！")
        except Exception as e:
            await upload.send(f"第{count}/{total}张图片上传失败！\n出错：{str(e)}")

    await upload.finish('上传已完毕')
