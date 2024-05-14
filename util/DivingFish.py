import aiohttp

from util.Config import config


async def get_player_data(qq: str):
    payload: dict[str, any] = {"qq": qq, "b50": True}
    async with aiohttp.ClientSession() as session:
        async with session.post(
                "https://www.diving-fish.com/api/maimaidxprober/query/player", json=payload
        ) as resp:
            if resp.status == 400:
                return None, 400
            if resp.status == 403:
                return None, 403
            obj: object = await resp.json()
            return obj, 200


async def get_player_records(qq: str):
    headers: dict[str, str] = {"Developer-Token": config.dev_token}
    payload: dict[str, str] = {"qq": qq}
    async with aiohttp.ClientSession() as session:
        async with session.get(
                "https://www.diving-fish.com/api/maimaidxprober/dev/player/records",
                headers=headers,
                params=payload,
        ) as resp:
            if resp.status == 400:
                return None, 400
            obj: object = await resp.json()
            return obj, 200


async def get_player_record(qq: str, music_id):
    headers: dict[str, str] = {"Developer-Token": config.dev_token}
    payload: dict[str, str] = {"qq": qq, "music_id": music_id}
    async with aiohttp.ClientSession() as session:
        async with session.post(
                "https://www.diving-fish.com/api/maimaidxprober/dev/player/record",
                headers=headers,
                json=payload,
        ) as resp:
            if resp.status == 400:
                return None, 400
            obj: object = await resp.json()
            return obj, 200
