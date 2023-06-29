#!/usr/bin/python3
"""DAQ970シリーズをリモート操作します。
毎秒CHANに指定したチャンネルを測定します。
測定値がLIMITを下回ると ビープ音を鳴らして、画面を暗転します。
"""

import sys
import time
import logging
import math
from gpiozero import MCP3202
from gpiozero.pins.pigpio import PiGPIOFactory
# 自作 DAQ コントローラ
import pydaq

# Measure Option
WARNING = 1.8e3
# chanlist1 = "101:113"
# chanlist2 = "201:213"


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
stream_handler = logging.StreamHandler()
stream_handler .setLevel(logging.DEBUG)

# Set log format
formatter = CustomFormatter("[ %(levelname)s ] %(asctime)s: %(message)s")
stream_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(stream_handler)

# Initialize instruments
try:
    daq = pydaq.Daq()
except BaseException as e:
    logger.critical(e)
    sys.exit(1)

try:
    pushed_time = None
    limit: int = 0
    while True:
        #
        # vol1 = daq.measure("MEAS:VOL? (@120)")
        #
        command = (
            # Measure resistance
            f"CONF:RES 10E6,10, (@101:102)",
            # 10V以上の電圧があればスイッチが入っている(@120)で測らない
            # "CONF:RES 10E6,10, (@{})".format(chanlist2 if vol1>10 else chanlist1)
            "RES:NPLC 1",

            # Set alert state
            # Display Red font
            f"CALC:LIMIT:LOW {WARNING}",
            "CALC:LIMIT:LOW:STATE ON",
        )

        # DUMMY DATA
        res: list[float] = daq.measure(*command)
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

        # 毎秒測定
        time.sleep(1)

finally:
    # DAQ session handler close
    daq.write("STATUS:PRESET")
    daq.write("DISP:TEXT:CLEAR")
    daq.write("*CLS")
    daq.close()
