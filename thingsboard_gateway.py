from models import Sensors
from dirty.env import TG_TOKEN
import requests
import dataclasses

def on_new_read(new_read: Sensors):
    print(f"[TG_GW]: {new_read}; token={TG_TOKEN}", flush=True)
    res = requests.post(
        url=f"http://thingsboard.cloud/api/v1/{TG_TOKEN}/telemetry",
        json=dataclasses.asdict(new_read)
    )
    if res.status_code > 299:
        print('failed to send', flush=True)
        print(res.json(), flush=True)
    else:
        print(res.status_code, flush=True)
