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
WARNING = 2000


def read_volume_resistance() -> int:
    """MP3202に流れる電圧を読み取る。
    電圧は可変抵抗により0V~3.3Vまで変化する。
    可変抵抗の回転角に依存する割合0.0~1.0を返す。
        3.3Vなら1.0
        0.0Vなら0.0
    が返る。

    typical 200kΩ ~ 1MΩ
    最大3MΩまで設定できる
    """
    step = 10000  # kΩオーダー & step 10kΩ
    max_val = 3.3e6  # limit調整可能値 <3.3MΩ
    try:
        factory = PiGPIOFactory()
        adc_ch0 = MCP3202(channel=0, max_voltage=3.3, pin_factory=factory)
        val: float = adc_ch0.value  # 0～1
    finally:
        factory.close()
    kohm: int = math.floor(max_val / step * val**2)  # 0~330 小数点以下切り捨て
    # 指数関数でカーブを付けて低い値で調整しやすく
    return kohm * step


def measure_unless_working(vol: int, start_chan: int, end_chan: int) -> list[float]:
    """ 電圧がかかっていない方のモジュールの抵抗値を測定する
    volで与えられたチャンネルの電圧を測定する
    電圧が10V未満であれば、接続されているので抵抗値を測ってはいけない。
    (抵抗値を測っても参考にならない。機材が破損するわけではない。)
    start_chanからend_chanで与えられたチャンネルの抵抗値を測定する。
    """
    # 10V以上の電圧があればスイッチが入っているので測らない
    is_working = daq.voltage(vol) > 10
    if is_working:
        return []

    cmd = (
        "CONF:RES 10E6,10, (@{}:{})".format(start_chan, end_chan),
        "RES:NPLC 1",
        # Warning message on DAQ970A
        f"CALC:LIMIT:LOW {WARNING}",
        "CALC:LIMIT:LOW:STATE ON",
    )
    return daq.measure(*cmd, delay=12)

def error_check(index:int, res: list[float], limit:float) -> None:
    """ resの返り値の内１つでもlimitを下回ったらBeep
    """
    log_msg: str = ",".join(str(i) for i in [index] + res)
    # resの返り値の内１つでもlimitを下回ったら
    if any(r < limit for r in res):
        # Display ERROR message on DAQ970A
        # Beep と画面暗転
        daq.write("SYSTEM:BEEP")
        daq.write("DISP:TEXT '[ CAUTION ]\nSHUTDOWN THE SYSTEM'")
        logger.error(log_msg)
    # resの返り値の内１つでもWARNINGを下回ったら
    elif any(r < WARNING for r in res):
        # warning, info levelのときは画面暗転を解除
        daq.write("DISP:TEXT:CLEAR")
        logger.warning(log_msg)
    else:
        # warning, info levelのときは画面暗転を解除
        daq.write("DISP:TEXT:CLEAR")
        logger.info(log_msg)

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
stream_handler.setLevel(logging.DEBUG)

# Set log format
formatter = CustomFormatter("[ %(levelname)s ] %(asctime)s,%(message)s")
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
    limit: int = 0
    while True:
        # 10Vかかっていない方のモジュールの抵抗値を測定する
        # float リストか空のリストが返ってくる
        chan = (
                (120, 101, 113),
                (220, 201, 213),
                )
        for i,c in enumerate(chan, 1):
            res = measure_unless_working(*c)
            error_check(i, res, limit)


        # 制限値を可変抵抗の回し角から読み込む
        new_limit = read_volume_resistance()
        if limit != new_limit:
            limit = new_limit
            # 表示は右詰め、kΩ表示、小数点以下切り捨て
            display_limit_str = "{:>6d}kOhm".format(int(limit / 1000))
            logger.debug(f"Limit value changed: {display_limit_str}")
            daq.write(f"DISP:TEXT 'Set alarm {display_limit_str}'")

        # 毎秒測定
        time.sleep(1)

finally:
    # DAQ session handler close
    daq.write("STATUS:PRESET")
    daq.write("DISP:TEXT:CLEAR")
    daq.write("*CLS")
    daq.close()
