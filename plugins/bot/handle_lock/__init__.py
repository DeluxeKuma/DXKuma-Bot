from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    GroupIncreaseNoticeEvent,
    GroupDecreaseNoticeEvent,
)
from nonebot.adapters.onebot.v11.exception import ActionFailed
from nonebot.message import event_preprocessor, run_postprocessor, event_postprocessor

from util.Config import config
from util.exceptions import NotAllowedException, NeedToSwitchException, SkipException
from .util import locks, Lock, States


@event_preprocessor
async def _(
    bot: Bot,
    event: GroupMessageEvent | GroupIncreaseNoticeEvent | GroupDecreaseNoticeEvent,
):
    if event.is_tome():
        return

    key = f"{event.group_id}{event.user_id}{event.time}".__hash__()
    if key not in locks:
        locks[key] = Lock()

    locks[key].count += 1
    await locks[key].semaphore.acquire()
    locks[key].count -= 1
    if locks[key].state == States.PROCESSED or (
        bot.self_id not in config.allowed_accounts
        and (
            (locks[key].state == States.SKIPED)
            or (locks[key].count > 0 and locks[key].state == States.NEED_TO_SWITCH)
        )
    ):
        locks[key].semaphore.release()
        raise SkipException

    return


@run_postprocessor
async def _(
    event: GroupMessageEvent | GroupIncreaseNoticeEvent | GroupDecreaseNoticeEvent,
    exception: Exception | None,
):
    if event.is_tome():
        return

    key = f"{event.group_id}{event.user_id}{event.time}".__hash__()
    if isinstance(exception, NotAllowedException) or isinstance(
        exception, ActionFailed
    ):
        locks[key].state = States.SKIPED
        locks[key].semaphore.release()
        return

    if isinstance(exception, NeedToSwitchException):
        locks[key].state = States.NEED_TO_SWITCH
        locks[key].semaphore.release()
        return

    locks[key].state = States.PROCESSED


@event_postprocessor
async def _(
    event: GroupMessageEvent | GroupIncreaseNoticeEvent | GroupDecreaseNoticeEvent,
):
    if event.is_tome():
        return

    key = f"{event.group_id}{event.user_id}{event.time}".__hash__()
    if locks[key].state == States.PROCESSED:
        locks[key].semaphore.release()
        if locks[key].count <= 0:
            locks.pop(key)
