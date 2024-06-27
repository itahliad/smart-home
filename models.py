from dataclasses import dataclass

@dataclass(frozen=True)
class Sensors:
    time: int
    fan_speed: int
    temperature_c: float
    gas_level: int
    light_level: int
