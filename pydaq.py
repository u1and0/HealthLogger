"""
Keysight 測定器を操作する

Keysight測定器のプログラムリファレンス
https://www.batronix.com/files/Keysight/DAQ/DAQ970A-973A-Programming.pdf

case insensitive なので upper caseでも lower caseでもコマンドを受け付けるが、
このコードではupper caseで統一して記述します。
"""
import time
from typing import Union, Optional
from enum import Enum
import pyvisa


class Range(Enum):
    AUTO = "AUTO"
    MIN = "MIN"
    MAX = "MIN"
    DEF = "DEF"

    def __str__(self):
        return self.name.upper()


class Resolution(Enum):
    MIN = "MIN"
    MAX = "MAX"
    DEF = "DEF"

    def __str__(self):
        return self.name.upper()


class Daq:
    """ Keysight DAQ970A/DAQ973A controller """

    def __init__(self):
        """ リソースの開放
        ポートをスキャンして
        USB から始まるポートに割当て。

        インタープリターでやっているときはcloseしないと
        他のセッションからアクセスできなくなるので注意

        Usage:
            >>> daq = Daq()
            Check resources...
            ASRL/dev/ttyAMA0::INSTR
            USB0::10893::34305::MY59002752::0::INSTR
            initialize success.
            >>> daq.whoami
            'Keysight Technologies,DAQ973A,MY59002752,A.02.02-01.00-02.01-00.02-02.00-03-03\n'

        open_resource()で作成してインスタンスへアクセスするには
        daq.instr.{method}を使ってください。
        >>> daq.instr.write("MEAS:VOLT:DC? AUTO,DEF, (@110)")
        32
        >>> daq.instr.read()
        '+3.29713452E+00\n'

        """
        # Begin finding out the daq resources that are available.
        self.rm = pyvisa.ResourceManager()
        # Make a variable that is the list of visa devices attached to the computer.
        resources = self.rm.list_resources()
        print("Check resources...")

        for r in resources:
            print(r)
            if r.startswith("USB"):
                self.instr = self.rm.open_resource(r)
                print("initialize success.")
                break

        # 型式を取得
        # 'Keysight Technologies,DAQ973A,MY59002752,A.02.02-01.00-02.01-00.02-02.00-03-03\n'
        self.whoami = self.hello()

    def hello(self):
        return self.instr.query("*IDN?")

    def close(self):
        """ 他のセッションからアクセスするためにはリソースを閉じなければならない """
        self.rm.close()

    def __del__(self):
        self.close()

    @staticmethod
    def parse_string(*ch: Union[str, int]) -> str:
        """
        101,102,... のようにカンマで結合した文字列に変換
        >>> Daq.parse_string(101, 102)
        "101,102"
        """
        # :が含まれていたら 101:110 のようなリスト形式で指定されたものとする
        if ":" in (sch := "".join(str(c) for c in ch)):
            return sch
        return ",".join(str(c) for c in ch)

    @staticmethod
    def parse_float(st: str) -> Union[float, list[float]]:
        """
        '+1.99674538E+03,+2.63265505E+04' という文字列をカンマで区切って
        floatとして解釈し floatのリストで返す
        >>> Daq.parse_float('+1.99674538E+03,+2.63265505E+04' )
        [1996.74,26326.55]
        """
        # rstrip()で\nを削除して,で区切ってfloatリストにする
        lst = [float(r) for r in st.rstrip().split(",")]
        if len(lst) < 2:
            return lst[0]
        return lst

    def resistance(
        self,
        *ch: Union[int, str],
        range_: Union[Range, int] = Range.AUTO,
        resolution: Union[Resolution, int] = Resolution.DEF
    ) -> Union[float, list[float]]:
        """ 抵抗測定
        # 1の基板の01の抵抗を測定
        >>> daq.resistance(101)

        # 2の基板の01と03の抵抗を測定
        >>> daq.resistance(201, 203)

        # 1の基板の01から03の抵抗を測定
        >>> daq.resistance("101:103")
        chにはチャネル番号、基板1なら101～120まで、基板2なら201～220まで。

        NOTE: Keysightの仕様により、channel listは昇順ソートされる。
        よって、以下のように降順やバラバラの順番にchannelを渡しても
        ソートされるので、返ってくる値は同じ

        >>> daq.resistance(102,101)
        [1996.75952, 99.39895]

        >>> daq.resistance(101,102)
        [1996.76062, 99.3987556]
        """
        chs = Daq.parse_string(*ch)
        res = self.instr.query(
            f"MEAS:RES? {range_},{resolution}, (@{chs})")
        ary = Daq.parse_float(res)
        return ary

    def voltage(
        self,
        *ch: Union[int, str],
        range_: Union[Range, int] = Range.AUTO,
        resolution: Union[Resolution, int] = Resolution.DEF
    ) -> Union[float, list[float]]:
        """ 抵抗測定
        # 1の基板の01の抵抗を測定
        >>> daq.resistance(101)

        # 2の基板の01と03の抵抗を測定
        >>> daq.resistance(201, 203)

        chにはチャネル番号、基板1なら101～120まで、基板2なら201～220まで。
        """
        chs = Daq.parse_string(*ch)
        res = self.instr.query(
            f"MEAS:VOLT:DC? {range_},{resolution}, (@{chs})")
        return Daq.parse_float(res)

    def measure(self, *message: str, delay: float = 0.0, **kwargs):
        """queryの結果をfloatにパースする"""
        res = self.query(*message, delay=delay, **kwargs)
        return Daq.parse_float(res)

    def query(self, *message: str, delay: float = 0.0,
            delay: float = 0.0,
            termination: Optional[str] = None,
            encoding: Optional[str] = None):
        """Send any command to DAQ

        ex)
        Channel 101の抵抗値をrange:Auto, resolution: Defaultで測定する
        >>> daq.query("MEAS:RES? AUTO,DEF, (@101)")
        '+1.99672270E+03\n'

        RES?のあとにスペース入れないとエラー

        Returns will be raw string included newline "\n".
        """
        # Write all messages one by one
        for command in message:
            self.instr.write(command,
                    termination=termination,
                    encoding=encoding)

        # Finally read buffer from instrument
        self.instr.write("READ?")

        # Wait for command processing
        if delay > 0.0:
            time.sleep(delay)

        return self.instr.read(termination=termination,
                    encoding=encoding)
)

    def write(self, *args, **kwargs):
        """ Same as daq.instr.write()
        >>> daq.write("MEAS:VOLT:DC? AUTO,DEF, (@110)")

        誤情報。
        ~~`daq.write()`を複数行入れるときは一つの関数に入れられる~~
        >>> daq.write("MEAS:VOLT:DC? AUTO,DEF, (@110)", "read?")

        positional引数は1つしか受け付けない。
        >>> daq.write("MEAS:VOLT:DC? AUTO,DEF, (@110)")
        >>> daq.write("read?")
        >>> daq.read()

        代わりに`\n`で区切れば(DAQ973Aの場合は？)複数コマンド入れられる。

        >>> daq.write("MEAS:VOLT:DC? AUTO,DEF, (@110)\nread?")
        >>> daq.read()

        write(), read()を打つのが冗長なので、query()を打つことがほとんど。
        query()は内部でwrite, read()を行っている。
        """
        return self.instr.write(*args, **kwargs)

    def read(self, *args, **kwargs):
        """ Same as daq.instr.read()
        write()したバッファを読み込む。

        >>> response = daq.read()
        >>> Daq.parse_float(response)
        3.3245
        """
        return self.instr.read(*args, **kwargs)
