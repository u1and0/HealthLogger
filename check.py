#!/usr/bin/python3
"""DAQ970シリーズをリモート操作します。
毎秒CHANに指定したチャンネルを測定します。
測定値がLIMITを下回ると ビープ音を鳴らして、画面を暗転します。

Toggle led(GPIO17) HIGH / LOW by push switch(GPIO18)

,--------------------------------.
| oooooooooooooooooooo J8   +======
| 1ooooooooooooooooooo  PoE |   Net
|  Wi                    1o +======
|  Fi  Pi Model 4B  V1.5 oo      |
|        ,----. +---+         +====
| |D|    |SoC | |RAM|         |USB3
| |S|    |    | |   |         +====
| |I|    `----' +---+            |
|                   |C|       +====
|                   |S|       |USB2
| pwr   |hd|   |hd| |I||A|    +====
`-| |---|m0|---|m1|----|V|-------'

J8:
   3V3  (1) (2)  5V
 GPIO2  (3) (4)  5V
 GPIO3  (5) (6)  GND
 GPIO4  (7) (8)  GPIO14
   GND  (9) (10) GPIO15
    `--------------------------------`
GPIO17 (11) (12) GPIO18  -- SWITCH --|
    `---------------------- LED    --'
GPIO27 (13) (14) GND
GPIO22 (15) (16) GPIO23
   3V3 (17) (18) GPIO24
GPIO10 (19) (20) GND
 GPIO9 (21) (22) GPIO25
GPIO11 (23) (24) GPIO8
   GND (25) (26) GPIO7
 GPIO0 (27) (28) GPIO1
 GPIO5 (29) (30) GND
 GPIO6 (31) (32) GPIO12
GPIO13 (33) (34) GND
GPIO19 (35) (36) GPIO16
GPIO26 (37) (38) GPIO20
   GND (39) (40) GPIO21

POE:
TR01 (1) (2) TR00
TR03 (3) (4) TR02

For further information, please refer to https://pinout.xyz/
"""

import sys
import time
import logging
import math
# Raspi GPIO制御
import RPi.GPIO as GPIO
from gpiozero import MCP3202
from gpiozero.pins.pigpio import PiGPIOFactory
# 自作 DAQ コントローラ
import pydaq

# Pin setting
led_pin = 17
switch_pin = 18
# GPIO setting
GPIO.setmode(GPIO.BCM)
# set IN mode and enable pull up
GPIO.setup(switch_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(led_pin, GPIO.OUT)  # set OUT mode
GPIO.output(led_pin, GPIO.LOW)  # default OFF

# for closure
pushed_time = None


# Measure Option
# LIMIT = 1.1e3
WARNING = 1.8e3
CHAN = "101:113"
# chanlist1 = "101:113"
# chanlist2 = "201:213"


def blink():
    """blink 5 times per 0.5 sec"""
    for _ in range(5):
        GPIO.output(led_pin, GPIO.HIGH)
        time.sleep(0.5)
        GPIO.output(led_pin, GPIO.LOW)
        time.sleep(0.5)


def read_volume_resistance() -> int:
    """MP3202に流れる電圧を読み取る。
    電圧は可変抵抗により0V~3.3Vまで変化する。
    可変抵抗の回転角に依存する割合0.0~1.0を返す。
        3.3Vなら1.0
        0.0Vなら0.0
    が返る。

    typical 200kΩ ~ 1MΩ
    最大3MΩまで設定できる

    1000倍してintを取って1kΩ未満の変動は無視する
    更に3000倍して最大3000kオームまで設定可能
    """
    step = 3e3  # 制限値の最大: 3000kΩ
    try:
        factory = PiGPIOFactory()
        adc_ch0 = MCP3202(channel=0, max_voltage=3.3, pin_factory=factory)
        val: float = adc_ch0.value  # 分母は0～1
        kohm: int = math.floor(val*1000)  # 0~1000 小数点以下切り捨て
    finally:
        factory.close()
    return kohm * step


class CustomFormatter(logging.Formatter):
    """[WARNING] -> [WARN] のように表示を先頭4文字に変更するカスタムフォーマッタ"""

    def format(self, record):
        record.levelname = record.levelname[:4]
        return super().format(record)


# Logging option
# Set log level
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Set stream handler
stream_handler = logging.FileHandler("output.log", "w", "utf-8")
stream_handler.setLevel(logging.DEBUG)

# Set file handler
file_handler = logging.StreamHandler()
file_handler .setLevel(logging.DEBUG)

# Set log format
formatter = CustomFormatter("[ %(levelname)s ] %(asctime)s: %(message)s")
stream_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(stream_handler)
logger.addHandler(file_handler)

# Initialize instruments
try:
    daq = pydaq.Daq()
except BaseException as e:
    logger.critical(e)
    sys.exit(1)

try:
    limit: int = 0
    while True:
        #
        # vol1 = daq.measure("MEAS:VOL? (@120)")
        #
        command = (
            # Measure resistance
            f"CONF:RES 10E6,10, (@{CHAN})",
            # 10V以上の電圧があればスイッチが入っている(@120)で測らない
            # "CONF:RES 10E6,10, (@{})".format(chanlist2 if vol1>10 else chanlist1)
            "RES:NPLC 1",

            # Set alert state
            # Display Red font
            f"CALC:LIMIT:LOW {WARNING}",
            "CALC:LIMIT:LOW:STATE ON",
        )

        # DUMMY DATA
        res: list[float] = [1e10]  # daq.measure(*command)
        res_csv: str = ",".join(str(i) for i in res)

        # resの返り値の内１つでもlimitを下回ったら
        if any(r < limit for r in res):
            # Beep と画面暗転
            daq.write("SYSTEM:BEEP")
            daq.write("DISP:TEXT '[ CAUTION ]\nSHUTDOWN THE SYSTEM'")
            logger.error(res_csv)
        # resの返り値の内１つでもWARNINGを下回ったら
        elif any(r < WARNING for r in res):
            # warning, info levelのときは画面暗転を解除
            daq.write("DISP:TEXT:CLEAR")
            logger.warning(res_csv)
        else:
            # warning, info levelのときは画面暗転を解除
            daq.write("DISP:TEXT:CLEAR")
            logger.info(res_csv)

        # 制限値を可変抵抗の回し角から読み込む
        new_limit = read_volume_resistance()
        if limit != new_limit:
            limit = new_limit
            display_limit_str = "{:>6d}kOhm".format(int(limit/1000))
            print(f"Limit value changed: {display_limit_str}")
            # 表示は右詰め、kΩ表示、小数点以下切り捨て
            daq.write(f"DISP:TEXT 'Set alarm {display_limit_str}'")

        # ボタンを押した瞬間の検出
        if GPIO.input(switch_pin) == GPIO.LOW and pushed_time is None:
            pushed_time = time.time()

        # ボタンを離した瞬間の検出
        if GPIO.input(switch_pin) == GPIO.HIGH and pushed_time is not None:
            button_duration = time.time() - pushed_time

            if button_duration < 1.0:
                logger.warning("Receiving reboot signal.")
                blink()  # 短押しで点滅
                # subprocess.run(["reboot"])
            else:
                logger.warning("Receiving shutdown signal.")
                GPIO.output(led_pin, GPIO.HIGH)  # 長押しで点灯
                # subprocess.run(["shutdown","-h","0"])

            # スイッチを離したらタイムスタンプをリセット
            pushed_time = None

        # 毎秒測定
        time.sleep(1)

finally:
    # DAQ session handler close
    daq.write("STATUS:PRESET")
    daq.write("DISP:TEXT:CLEAR")
    daq.write("*CLS")
    daq.close()
    # GPIO開放
    GPIO.cleanup()
