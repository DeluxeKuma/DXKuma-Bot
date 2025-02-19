import asyncio
import datetime
import os
import re
import shelve
from pathlib import Path
from random import SystemRandom

from PIL import Image, UnidentifiedImageError
from dill import Pickler, Unpickler
from nonebot import on_regex
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment

from util.Config import config
from util.exceptions import NotAllowedException

shelve.Pickler = Pickler
shelve.Unpickler = Unpickler

random = SystemRandom()

rand_pic = on_regex(r"^(随机)?(迪拉熊|dlx)((涩|色|瑟)图|st)?$", re.I)
rank = on_regex(r"^(迪拉熊|dlx)(排行榜|rank)$", re.I)

PICPATH = "./Static/Gallery/SFW/"
PICPATH_NSFW = "./Static/Gallery/NSFW/"
DATA_PATH = "./data/pic_times/"


def get_time():
    today = datetime.date.today()

    # 获取当前年份
    year = today.year

    # 获取当前日期所在的周数
    week_number = today.isocalendar()[1]

    # 将年份和周数拼接成字符串
    result = str(year) + str(week_number)
    return result


def update_count(qq: str, type: str):
    time = get_time()

    with shelve.open(f"{DATA_PATH}{time}.db") as count_data:
        if qq not in count_data:
            count = count_data.setdefault(qq, {"sfw": 0, "nsfw": 0})
        else:
            count = count_data[qq]

        count[type] += 1
        count_data[qq] = count


def gen_rank(time):
    leaderboard = list()

    with shelve.open(f"{DATA_PATH}{time}.db") as data:
        for qq, qq_data in data.items():
            total_count = qq_data["sfw"] + qq_data["nsfw"]
            leaderboard.append((qq, total_count))

    leaderboard.sort(key=lambda x: x[1], reverse=True)

    return leaderboard[:5]


def check_image(imgpath: Path):
    try:
        image = Image.open(imgpath)
    except UnidentifiedImageError:
        return False
    try:
        image.verify()
    except OSError:
        return False
    image.close()
    return True


@rand_pic.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    qq = event.get_user_id()
    msg = event.get_plaintext()
    type = "sfw"
    path = PICPATH
    if re.search(r"(涩|色|瑟)图|st", msg, re.I):
        type = "nsfw"
        path = PICPATH_NSFW
    if type == "nsfw":
        if os.path.exists("./data/nsfw_lock"):
            await rand_pic.send("由于该账号被警告，该功能暂时关闭，请稍后再试mai~")
            return
        if bot.self_id not in config.allowed_accounts:  # type 为 'nsfw' 且非指定机器人
            raise NotAllowedException
    elif group_id == config.special_group:  # 不被限制的 group_id
        pass
    else:
        weight = random.randint(0, 9)
        if weight == 0:
            if type == "sfw":
                msg = MessageSegment.text(
                    "迪拉熊提醒你：注意不要过度刷屏，给其他人带来麻烦哦，再试一下吧~"
                )
            elif type == "nsfw":
                msg = MessageSegment.text(
                    "哼哼，迪拉熊的魅力这么大嘛，但是也要注意节制哦~"
                )
            await rand_pic.finish(msg)

    files = os.listdir(path)
    if not files:
        msg = (
            MessageSegment.text("迪拉熊不准你看"),
            MessageSegment.image(Path("./Static/Gallery/0.png")),
        )
        await rand_pic.finish(msg)
    for _ in range(3):
        file = random.choice(files)
        pic_path = os.path.join(path, file)
        if check_image(pic_path):
            break
    else:
        msg = (
            MessageSegment.text("迪拉熊不准你看"),
            MessageSegment.image(Path("./Static/Gallery/0.png")),
        )
        await rand_pic.finish(msg)
    with open(pic_path, "rb") as fd:
        send_msg = await rand_pic.send(MessageSegment.image(fd.read()))
    update_count(qq=qq, type=type)
    if type == "nsfw":
        msg_id = send_msg["message_id"]
        asyncio.create_task(delete_msg(bot, 10, msg_id))


async def delete_msg(bot, sec, message_id):
    await asyncio.sleep(sec)
    await bot.delete_msg(message_id=message_id)


@rank.handle()
async def _(bot: Bot):
    time = get_time()

    leaderboard = gen_rank(time)

    leaderboard_output = list()
    count = min(len(leaderboard), 5)  # 最多显示5个人，取实际人数和5的较小值
    for i, (qq, total_count) in enumerate(leaderboard[:count], start=1):
        user_name = (await bot.get_stranger_info(user_id=qq))["nickname"]
        rank_str = f"{i}. {user_name}：{total_count}"
        leaderboard_output.append(rank_str)

    msg = "\r\n".join(leaderboard_output)
    msg = f"本周迪拉熊厨力最高的人是……\r\n{msg}\r\n迪拉熊给上面{count}个宝宝一个大大的拥抱~\r\n（积分每周重算）\r\n\r\n图库：{len(os.listdir(PICPATH))}:{len(os.listdir(PICPATH_NSFW))}"
    await rank.finish(msg)
