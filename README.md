# 初期設定

## インストール
リポジトリをクローンし、依存ライブラリをインストールします。

```
$ git clone https://github.com/u1and0/HealthLogger
$ pip install -r requirements.txt
```

## 依存関係
* pyusb
* pyvisa
* pyvisa-py
* pigpio

## 測定器の配線

```
        [Rasberry Pi]
              |
              |
------------------------------
|       [DAQ970A(DAQ973A)]   |
|                            |
|  [DAQM901A] | | [DAQM901A] |
------------------------------
      | |             | |
      | |             | |
          [ 端子盤 ]
              | |
              | |
          [ 測定対象 ]

```


## ラズパイの配線
下図のようにGPIO26とGNDの間にLED, GPIO21とGNDの間にスイッチを配置します。

```

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
        GPIO17 (11) (12) GPIO18
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
   /--- GPIO26 (37) (38) GPIO20
  LED
    \----- GND (39) (40) GPIO21  ---\
            |_________/ o___________|

(SCL) o|----------|
(SDA) o| pFc8563  |
(GND) o| Module   |
(Vcc) o|----------|

                    |-----|
      [ GND ]--( 4 )|     |( 5 )---GPIO10 (19)
      [ NC ]   ( 3 )| MCP |( 6 )--- GPIO9 (21)
  Volume( 2 )--( 2 )|3202 |( 7 )---GPIO11 (23)
      [ NC ]   ( 1 )|     |( 8 )---[ 3.3V ]
                    |-----|

  Volume( 1 ) -- [ GND ]
  Volume( 3 ) -- [ 3.3V ]

```


## 初期設定
/boot/config.txtと/etc/rc.localに次のように書き込みます。(必要な部分だけ抽出しています。)
省略した部分は`# ...snip`と表記しています。

1. SPIインターフェースを有効化
1. /boot/config.txtでRTCを登録
1. GPIO21とGNDの間にスイッチを設けて、1000ms以上長押しするとshutdownシグナルを送る
1. shutdownするとGPIO26がLOW(LED消灯)


### 可変抵抗値の読み取り
ボリューム抵抗によって抵抗値のリミットを調整します。

1. SPIインターフェースを有効化します。
`$ sudo raspi-config`
interface -> SPI -> enable -> finish

1. pigpioデーモンを有効化します。

```
$ sudo apt install pigpio
$ sudo service pigpiod start
$ sudo systemctl enable pigpiod.service
```

### RTCを登録

```/boot/config.txt
# ...snip

[all]
# RTC としてPCF8563を登録
dtoverlay=i2c-rtc,pcf8563
# 1000ms以上gpio21番ピンとGNDに導通があるとshutdownシグナルを送る
dtoverlay=gpio-shutdown,gpio_pin=21,debounce=1000
# シャットダウン後にLOWになる。デフォルトでGPIO26
dtoverlay=gpio-poweroff,active_low=1

# ...snip
```

* ハードウェアクロックから時刻を読み込みます。
* DAQ970を実行するPythonスクリプトを実行します。

```/etc/rc.local
# ...snip

# Set system date by HW Clock PCF8563
# echo pcf8563 0x51 > /sys/class/i2c-adapter/i2c-1/new_device
# sleep 1
hwclock -s

# 自動計測スクリプトの起動
# poetry run uvicorn /home/zig/Program/python/health_dashboard/main:app --port 8880 --host=0.0.0.0

# sudo pip install pyvisa pyvisa-py pyusb
/usr/bin/python3 /home/zig/Program/python/HealthLogger/check.py >> /var/log/health_logger_check$(date +%Y%m%d_%H%M%S).log 2>&1

exit 0
```


`hwclock -s`でRTCから時刻を読み込み、システムクロックに書き込みます。
raspberry piはデフォルトで時刻を保持しません。NTPサーバー任せです
今回のケースではオフラインで稼働させますので、NTPサーバーの代わりとして、RTCから時刻を取得します。


ラズパイにはシャットダウンする機構がデフォルトでは設けられていません。基本的にはターミナルから`shutdown -h 0`や`poweroff`コマンドを実行します。
今回のケースではターミナルは表示できませんので、シャットダウンボタンを設けました。上記設定でGPIO21をGNDに1000ms以上通があると、shutdownシグナルを送信します。
逆に、raspiアクティブ時にはLED点灯します。転倒時に測定器の電源を落とさないでください。


# 実行
## 運用手順
### スタート
1. 測定器DAQ970A(973A)の電源をONにします。
1. USBによる給電で、続いてラズパイが自動的に起動します。
1. 上記設定で、自動的に測定が始まります。

### ストップ

1. ラズパイの基板上にあるスイッチを1秒以上長押しします。するとシャットダウンシグナルをOS経送ります。  シャットダウンを受信するとLEDが点滅します。5秒ほどでLEDが消灯します。
1. 測定器の電源を1秒以上長押しして、電源を切ります。

注意: ラズパイの基板上のLEDが点灯している間は測定中ですので、電源を切らないでください。


## メインの制御
`check.py`で実行します。


## 測定器の制御
`pydaq.py`で制御します。


## ログ
`check.py`は標準出力に下記のような形式でログを書き出します。
`/etc/rc.local`に書いたリダイレクトで、標準出力と標準エラー出力に`/var/log/health_logger_check20221222_205547.log`のようなファイル名でcsvライクな形式で書き込まれます。
ただし、`[INFO] <日時>: 測定値1, 測定値2, ...測定値N`の形式です。 checkの後の数字は日時で`YYYYmmdd_HHMMSS`の形式です。


```
[ INFO ] 2023-06-29 10:44:30,509: 9946.14871,9.9e+37
[ INFO ] 2023-06-29 10:44:32,946: 9950.95788,9.9e+37
[ INFO ] 2023-06-29 10:44:37,834: 9949.53803,9.9e+37
...
[ ERRO ] 2022-12-22 20:56:26,265: 9954.80522,9962.13349
[ ERRO ] 2022-12-22 20:56:47,934: 9955.81286,9962.95792
```
