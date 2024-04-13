import json
from pathlib import Path

maimai_src = Path('./src/maimai/')
maimai_Class = maimai_src / 'Class'
maimai_Dani = maimai_src / 'Dani'
maimai_Frame = maimai_src / 'Frame'
maimai_Plate = maimai_src / 'Plate'
maimai_Rating = maimai_src / 'Rating'


with open('/home/ubuntu/DXKuma-Bot/src/maimai/songList.json', 'r') as f:
    songList = json.load(f)