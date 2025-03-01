# -*- coding: utf-8 -*-
# Copyright (c) 2021 Tachibana Securities Co., Ltd. All rights reserved.

# 2021.07.08,   yo.
# 2023.4.18 reviced,   yo.
# Python 3.6.8 / centos7.4
# API v4r3 で動作確認
# 立花証券ｅ支店ＡＰＩ利用のサンプルコード
# 機能: ログイン、日足株価取得、ログアウト を行ないます。
#
# 利用方法: コード後半にある「プログラム始点」以下の設定項目を自身の設定に変更してご利用ください。
#
# 参考資料（必ず最新の資料を参照してください。）--------------------------
#マニュアル
#「ｅ支店・ＡＰＩ、ブラウザからの利用方法」
# (api_web_access.xlsx)
# シート「マスタ・時価」
# ２－２．各Ｉ／Ｆ説明 
# （３）蓄積情報問合取得I/F
#
# == ご注意: ========================================
#   本番環境にに接続した場合、実際に市場に注文を出せます。
#   市場で約定した場合取り消せません。
# ==================================================
#

import urllib3
from datetime import datetime  # datetime.datetimeではなく、datetimeを直接使用
import json
import time
import sys
from pathlib import Path
import logging
from repository.stock_repository import StockRepository
import threading
from collections import deque
from threading import Lock
import signal
import pandas as pd
from lib.indicator_calculator import IndicatorCalculator



#--- 共通コード ------------------------------------------------------

# request項目を保存するクラス。配列として使う。
# 'p_no'、'p_sd_date'は格納せず、func_make_url_requestで生成する。
class class_req :
    def __init__(self) :
        self.str_key = ''
        self.str_value = ''
        
    def add_data(self, work_key, work_value) :
        self.str_key = work_key
        self.str_value = work_value


# 口座属性クラス
class class_def_cust_property:
    def __init__(self):
        self.sUrlRequest = ''       # request用仮想URL
        self.sUrlMaster = ''        # master用仮想URL
        self.sUrlPrice = ''         # price用仮想URL
        self.sUrlEvent = ''         # event用仮想URL
        self.sZyoutoekiKazeiC = ''  # 8.譲渡益課税区分    1：特定  3：一般  5：NISA     ログインの返信データで設定済み。 
        self.sSecondPassword = ''   # 22.第二パスワード  APIでは第２暗証番号を省略できない。 関連資料:「立花証券・e支店・API、インターフェース概要」の「3-2.ログイン、ログアウト」参照
        self.sJsonOfmt = ''         # 返り値の表示形式指定
        


# 機能: システム時刻を"p_sd_date"の書式の文字列で返す。
# 返値: "p_sd_date"の書式の文字列
# 引数1: システム時刻
# 備考:  "p_sd_date"の書式：YYYY.MM.DD-hh:mm:ss.sss
def func_p_sd_date(int_systime):
    str_psddate = ''
    str_psddate = str_psddate + str(int_systime.year) 
    str_psddate = str_psddate + '.' + ('00' + str(int_systime.month))[-2:]
    str_psddate = str_psddate + '.' + ('00' + str(int_systime.day))[-2:]
    str_psddate = str_psddate + '-' + ('00' + str(int_systime.hour))[-2:]
    str_psddate = str_psddate + ':' + ('00' + str(int_systime.minute))[-2:]
    str_psddate = str_psddate + ':' + ('00' + str(int_systime.second))[-2:]
    str_psddate = str_psddate + '.' + (('000000' + str(int_systime.microsecond))[-6:])[:3]
    return str_psddate


# JSONの値の前後にダブルクオーテーションが無い場合付ける。
def func_check_json_dquat(str_value) :
    if len(str_value) == 0 :
        str_value = '""'
        
    if not str_value[:1] == '"' :
        str_value = '"' + str_value
        
    if not str_value[-1:] == '"' :
        str_value = str_value + '"'
        
    return str_value
    
    
# 受けたテキストの１文字目と最終文字の「"」を削除
# 引数：string
# 返り値：string
def func_strip_dquot(text):
    if len(text) > 0:
        if text[0:1] == '"' :
            text = text[1:]
            
    if len(text) > 0:
        if text[-1] == '\n':
            text = text[0:-1]
        
    if len(text) > 0:
        if text[-1:] == '"':
            text = text[0:-1]
        
    return text
    


# 機能: URLエンコード文字の変換
# 引数1: 文字列
# 返値: URLエンコード文字に変換した文字列
# 
# URLに「#」「+」「/」「:」「=」などの記号を利用した場合エラーとなる場合がある。
# APIへの入力文字列（特にパスワードで記号を利用している場合）で注意が必要。
#   '#' →   '%23'
#   '+' →   '%2B'
#   '/' →   '%2F'
#   ':' →   '%3A'
#   '=' →   '%3D'
def func_replace_urlecnode( str_input ):
    str_encode = ''
    str_replace = ''
    
    for i in range(len(str_input)):
        str_char = str_input[i:i+1]

        if str_char == ' ' :
            str_replace = '%20'       #「 」 → 「%20」 半角空白
        elif str_char == '!' :
            str_replace = '%21'       #「!」 → 「%21」
        elif str_char == '"' :
            str_replace = '%22'       #「"」 → 「%22」
        elif str_char == '#' :
            str_replace = '%23'       #「#」 → 「%23」
        elif str_char == '$' :
            str_replace = '%24'       #「$」 → 「%24」
        elif str_char == '%' :
            str_replace = '%25'       #「%」 → 「%25」
        elif str_char == '&' :
            str_replace = '%26'       #「&」 → 「%26」
        elif str_char == "'" :
            str_replace = '%27'       #「'」 → 「%27」
        elif str_char == '(' :
            str_replace = '%28'       #「(」 → 「%28」
        elif str_char == ')' :
            str_replace = '%29'       #「)」 → 「%29」
        elif str_char == '*' :
            str_replace = '%2A'       #「*」 → 「%2A」
        elif str_char == '+' :
            str_replace = '%2B'       #「+」 → 「%2B」
        elif str_char == ',' :
            str_replace = '%2C'       #「,」 → 「%2C」
        elif str_char == '/' :
            str_replace = '%2F'       #「/」 → 「%2F」
        elif str_char == ':' :
            str_replace = '%3A'       #「:」 → 「%3A」
        elif str_char == ';' :
            str_replace = '%3B'       #「;」 → 「%3B」
        elif str_char == '<' :
            str_replace = '%3C'       #「<」 → 「%3C」
        elif str_char == '=' :
            str_replace = '%3D'       #「=」 → 「%3D」
        elif str_char == '>' :
            str_replace = '%3E'       #「>」 → 「%3E」
        elif str_char == '?' :
            str_replace = '%3F'       #「?」 → 「%3F」
        elif str_char == '@' :
            str_replace = '%40'       #「@」 → 「%40」
        elif str_char == '[' :
            str_replace = '%5B'       #「[」 → 「%5B」
        elif str_char == ']' :
            str_replace = '%5D'       #「]」 → 「%5D」
        elif str_char == '^' :
            str_replace = '%5E'       #「^」 → 「%5E」
        elif str_char == '`' :
            str_replace = '%60'       #「`」 → 「%60」
        elif str_char == '{' :
            str_replace = '%7B'       #「{」 → 「%7B」
        elif str_char == '|' :
            str_replace = '%7C'       #「|」 → 「%7C」
        elif str_char == '}' :
            str_replace = '%7D'       #「}」 → 「%7D」
        elif str_char == '~' :
            str_replace = '%7E'       #「~」 → 「%7E」
        else :
            str_replace = str_char

        str_encode = str_encode + str_replace
        
    return str_encode



# 機能： API問合せ文字列を作成し返す。
# 戻り値： url文字列
# 第１引数： ログインは、Trueをセット。それ以外はFalseをセット。
# 第２引数： ログインは、APIのurlをセット。それ以外はログインで返された仮想url（'sUrlRequest'等）の値をセット。
# 第３引数： 要求項目のデータセット。クラスの配列として受取る。
def func_make_url_request(auth_flg, \
                          url_target, \
                          work_class_req) :
    work_key = ''
    work_value = ''

    str_url = url_target
    if auth_flg == True :
        str_url = str_url + 'auth/'
    
    str_url = str_url + '?{\n\t'
    
    for i in range(len(work_class_req)) :
        work_key = func_strip_dquot(work_class_req[i].str_key)
        if len(work_key) > 0:
            if work_key[:1] == 'a' :
                work_value = work_class_req[i].str_value
            else :
                work_value = func_check_json_dquat(work_class_req[i].str_value)

            str_url = str_url + func_check_json_dquat(work_class_req[i].str_key) \
                                + ':' + work_value \
                                + ',\n\t'
               
        
    str_url = str_url[:-3] + '\n}'
    return str_url



# 機能: API問合せ。通常のrequest,price用。
# 返値: API応答（辞書型）
# 第１引数： URL文字列。
# 備考: APIに接続し、requestの文字列を送信し、応答データを辞書型で返す。
#       master取得は専用の func_api_req_muster を利用する。
def func_api_req(str_url): 
    # print('送信文字列＝')
    # print(str_url)  # 送信する文字列

    # APIに接続
    http = urllib3.PoolManager()
    req = http.request('GET', str_url)

    # 取得したデータを、json.loadsを利用できるようにstr型に変換する。日本語はshift-jis。
    bytes_reqdata = req.data
    str_shiftjis = bytes_reqdata.decode("shift-jis", errors="ignore")

    # print('返信文字列＝')
    # print(str_shiftjis)

    # JSON形式の文字列を辞書型で取り出す
    json_req = json.loads(str_shiftjis)

    return json_req



# ログイン関数
# 引数1: p_noカウンター
# 引数2: アクセスするurl（'auth/'以下は付けない）
# 引数3: ユーザーID
# 引数4: パスワード
# 引数5: 口座属性クラス
# 返値：辞書型データ（APIからのjson形式返信データをshift-jisのstring型に変換し、更に辞書型に変換）
def func_login(int_p_no, my_url, str_userid, str_passwd, class_cust_property):
    # 送信項目の解説は、マニュアル「立花証券・ｅ支店・ＡＰＩ（ｖ〇）、REQUEST I/F、機能毎引数項目仕様」
    # p2/46 No.1 引数名:CLMAuthLoginRequest を参照してください。
    
    req_item = [class_req()]
    str_p_sd_date = func_p_sd_date(datetime.now())     # datetime.datetime.now() から datetime.now() に変更

    str_key = '"p_no"'
    str_value = func_check_json_dquat(str(int_p_no))
    #req_item.append(class_req())
    req_item[-1].add_data(str_key, str_value)

    str_key = '"p_sd_date"'
    str_value = str_p_sd_date
    req_item.append(class_req())
    req_item[-1].add_data(str_key, str_value)

    str_key = '"sCLMID"'
    str_value = 'CLMAuthLoginRequest'
    req_item.append(class_req())
    req_item[-1].add_data(str_key, str_value)

    str_key = '"sUserId"'
    str_value = str_userid
    req_item.append(class_req())
    req_item[-1].add_data(str_key, str_value)
    
    str_key = '"sPassword"'
    str_value = str_passwd
    req_item.append(class_req())
    req_item[-1].add_data(str_key, str_value)
    
    # 返り値の表示形式指定
    str_key = '"sJsonOfmt"'
    str_value = class_cust_property.sJsonOfmt    # "5"は "1"（1ビット目ＯＮ）と"4"（3ビット目ＯＮ）の指定となり「ブラウザで見や易い形式」且つ「引数項目名称」で応答を返す値指定
    req_item.append(class_req())
    req_item[-1].add_data(str_key, str_value)

    # ログインとログイン後の電文が違うため、第１引数で指示。
    # ログインはTrue。それ以外はFalse。
    # このプログラムでの仕様。APIの仕様ではない。
    # URL文字列の作成
    str_url = func_make_url_request(True, \
                                     my_url, \
                                     req_item)
    # API問合せ
    json_return = func_api_req(str_url)
    # 戻り値の解説は、マニュアル「立花証券・ｅ支店・ＡＰＩ（ｖ〇）、REQUEST I/F、機能毎引数項目仕様」
    # p2/46 No.2 引数名:CLMAuthLoginAck を参照してください。

    int_p_errno = int(json_return.get('p_errno'))    # p_erronは、マニュアル「立花証券・ｅ支店・ＡＰＩ（ｖ〇ｒ〇）、REQUEST I/F、利用方法、データ仕様」を参照ください。
    if not json_return.get('sResultCode') == None :
        int_sResultCode = int(json_return.get('sResultCode'))
    else :
        int_sResultCode = -1
    # sResultCodeは、マニュアル
    # 「立花証券・ｅ支店・ＡＰＩ（ｖ〇ｒ〇）、REQUEST I/F、注文入力機能引数項目仕様」
    # (api_request_if_order_vOrO.pdf)
    # の p13/42 「6.メッセージ一覧」を参照してください。
    #
    # 時間外の場合 'sResultCode' が返らないので注意
    # 参考例
    # {
    #         "p_no":"1",
    #         "p_sd_date":"2022.11.25-08:28:04.609",
    #         "p_rv_date":"2022.11.25-08:28:04.598",
    #         "p_errno":"-62",
    #         "p_err":"システム、情報提供時間外。",
    #         "sCLMID":"CLMAuthLoginRequest"
    # }




    if int_p_errno ==  0 and int_sResultCode == 0:    # ログインエラーでない場合
        # ---------------------------------------------
        # ログインでの注意点
        # 契約締結前書面が未読の場合、
        # 「int_p_errno = 0 And int_sResultCode = 0」で、
        # sUrlRequest=""、sUrlEvent="" が返されログインできない。
        # ---------------------------------------------
        if len(json_return.get('sUrlRequest')) > 0 :
            # 口座属性クラスに取得した値をセット
            class_cust_property.sZyoutoekiKazeiC = json_return.get('sZyoutoekiKazeiC')
            class_cust_property.sUrlRequest = json_return.get('sUrlRequest')        # request用仮想URL
            class_cust_property.sUrlMaster = json_return.get('sUrlMaster')          # master用仮想URL
            class_cust_property.sUrlPrice = json_return.get('sUrlPrice')            # price用仮想URL
            class_cust_property.sUrlEvent = json_return.get('sUrlEvent')            # event用仮想URL
            bool_login = True
        else :
            print('契約締結前書面が未読です。')
            print('ブラウザーで標準Webにログインして確認してください。')
    else :  # ログインに問題があった場合
        print('p_errno:', json_return.get('p_errno'))
        print('p_err:', json_return.get('p_err'))
        print('sResultCode:', json_return.get('sResultCode'))
        print('sResultText:', json_return.get('sResultText'))
        print()
        bool_login = False

    return bool_login


# ログアウト
# 引数1: p_noカウンター
# 引数2: class_cust_property（request通番）, 口座属性クラス
# 返値：辞書型データ（APIからのjson形式返信データをshift-jisのstring型に変換し、更に辞書型に変換）
def func_logout(int_p_no, class_cust_property):
    # 送信項目の解説は、マニュアル「立花証券・ｅ支店・ＡＰＩ（ｖ〇）、REQUEST I/F、機能毎引数項目仕様」
    # p3/46 No.3 引数名:CLMAuthLogoutRequest を参照してください。
    
    req_item = [class_req()]
    str_p_sd_date = func_p_sd_date(datetime.now())     # datetime.datetime.now() から datetime.now() に変更

    str_key = '"p_no"'
    str_value = func_check_json_dquat(str(int_p_no))
    #req_item.append(class_req())
    req_item[-1].add_data(str_key, str_value)

    str_key = '"p_sd_date"'
    str_value = str_p_sd_date
    req_item.append(class_req())
    req_item[-1].add_data(str_key, str_value)

    str_key = '"sCLMID"'
    str_value = 'CLMAuthLogoutRequest'  # logoutを指示。
    req_item.append(class_req())
    req_item[-1].add_data(str_key, str_value)
    
    # 返り値の表示形式指定
    str_key = '"sJsonOfmt"'
    str_value = class_cust_property.sJsonOfmt    # "5"は "1"（ビット目ＯＮ）と"4"（ビット目ＯＮ）の指定となり「ブラウザで見や易い形式」且つ「引数項目名称」で応答を返す値指定
    req_item.append(class_req())
    req_item[-1].add_data(str_key, str_value)
    
    # ログインとログイン後の電文が違うため、第１引数で指示。
    # ログインはTrue。それ以外はFalse。
    # このプログラムでの仕様。APIの仕様ではない。
    # URL文字列の作成
    str_url = func_make_url_request(False, \
                                     class_cust_property.sUrlRequest, \
                                     req_item)
    # API問合せ
    json_return = func_api_req(str_url)
    # 戻り値の解説は、マニュアル「立花証券・ｅ支店・ＡＰＩ（ｖ〇）、REQUEST I/F、機能毎引数項目仕様」
    # p3/46 No.4 引数名:CLMAuthLogoutAck を参照してください。

    int_sResultCode = int(json_return.get('sResultCode'))    # p_erronは、マニュアル「立花証券・ｅ支店・ＡＰＩ（ｖ〇ｒ〇）、REQUEST I/F、利用方法、データ仕様」を参照ください。
    if int_sResultCode ==  0 :    # ログアウトエラーでない場合
        bool_logout = True
    else :  # ログアウトに問題があった場合
        bool_logout = False

    return bool_logout

#--- 以上 共通コード -------------------------------------------------


# 参考資料（必ず最新の資料を参照してください。）--------------------------
#マニュアル
#「ｅ支店・ＡＰＩ、ブラウザからの利用方法」
# (api_web_access.xlsx)
# シート「マスタ・時価」
# ２－２．各Ｉ／Ｆ説明 
# （３）蓄積情報問合取得I/F
#  を参照してください。


# 要求
# 1	sCLMID      CLMMfdsGetMarketPriceHistory
# 2	sIssueCode  対象の銘柄コード、１要求１銘柄指定。
# 3	sSizyouC    対象の市場コード（現在"00":東証のみ）、引数省略可能（デフォルト＝東証）。


# 応答
# No	項目	設定値								
# 1	sDate   日付（YYYYMMDD）								
# 2	pDOP	始値								
# 3	pDHP	高値								
# 4	pDLP	安値								
# 5	pDPP	終値								
# 6	pDV	出来高								
# 7	pDOPxK	株式分割換算係数で計算した該当値								
# 8	pDHPxK	株式分割換算係数で計算した該当値								
# 9	pDLPxK	株式分割換算係数で計算した該当値								
#10	pDPPxK	株式分割換算係数で計算した該当値								
#11	pDVxK	株式分割換算係数で計算した該当値						
#12	pSPUO	株式分割前単位	※株式分割日のみ設定
#13	pSPUC	株式分割後単位	※株式分割日のみ設定
#14	pSPUK	株式分割換算係数（pSPUO/pSPUC）   ※株式分割日のみ設定


#--------------------------------------
# 電文のサンプル
#
#
# JSON要求電文
# {
#	"p_no":"2",
#	"p_sd_date":"2022.11.22-14:36:41.028",
#	"sCLMID":"CLMMfdsGetMarketPriceHistory",
#	"sIssueCode":"7071",
#	"sSizyouC":"00",
#	"sJsonOfmt":"5"
# }
#
#
#--------------------------------------
# JSON応答電文
# {
#	"p_sd_date":"2022.11.22-14:36:41.439",
#	"p_no":"2",
#	"p_rv_date":"2022.11.22-14:36:41.332",
#	"p_errno":"0",
#	"p_err":"",
#	"sCLMID":"CLMMfdsGetMarketPriceHistory",
#	"sIssueCode":"7071",
#	"sSizyouC":"00",
#	"aCLMMfdsMarketPriceHistory":
#	[
#	{
#		"sDate":"20191009",
#		"pDOP":"4260",
#		"pDHP":"4450",
#		"pDLP":"4000",
#		"pDPP":"4170",
#		"pDV":"1863400",
#		"pDOPxK":"532.5",
#		"pDHPxK":"556.25",
#		"pDLPxK":"500",
#		"pDPPxK":"521.25",
#		"pDVxK":"14907200"
#	},
# ~~~~~~~~
# ~~~~~~~~
#	{
#		"sDate":"20220929",
#		"pDOP":"2418",
#		"pDHP":"2502",
#		"pDLP":"2380",
#		"pDPP":"2380",
#		"pDV":"187300",
#		"pDOPxK":"2418",
#		"pDHPxK":"2502",
#		"pDLPxK":"2380",
#		"pDPPxK":"2380",
#		"pDVxK":"187300",
#		"pSPUK":"0.5",
#		"pSPUO":"1",
#		"pSPUC":"2"
#	},
# ~~~~~~~~
# ~~~~~~~~
#	{
#		"sDate":"20221121",
#		"pDOP":"2921",
#		"pDHP":"2944",
#		"pDLP":"2867",
#		"pDPP":"2926",
#		"pDV":"302800",
#		"pDOPxK":"2921",
#		"pDHPxK":"2944",
#		"pDLPxK":"2867",
#		"pDPPxK":"2926",
#		"pDVxK":"302800"
#	}
#	]
# }

# --- 以上資料 --------------------------------------------------------



# 機能: 日足株価データ取得
# 返値： 辞書型データ（APIからのjson形式返信データをshift-jisのstring型に変換し、更に辞書型に変換）
# 引数1: p_no
# 引数2: 銘柄コード
# 引数3: 市場（現在、東証'00'のみ）
# 引数4: 口座属性クラス
# 備考: 銘柄コードは、通常銘柄、4桁。優先株等、5桁。例、伊藤園'2593'、伊藤園優先株'25935'
def func_get_daily_price(int_p_no,
                        str_sIssueCode,
                        str_sSizyouC,
                        class_cust_property
                        ):
    # 送信項目の解説は、マニュアル「立花証券・ｅ支店・ＡＰＩ（ｖ〇）、REQUEST I/F、機能毎引数項目仕様」
    # p4/46 No.5 引数名:CLMKabuNewOrder を参照してください。

    req_item = [class_req()]
    str_p_sd_date = func_p_sd_date(datetime.now())     # datetime.datetime.now() から datetime.now() に変更

    str_key = '"p_no"'
    str_value = func_check_json_dquat(str(int_p_no))
    #req_item.append(class_req())
    req_item[-1].add_data(str_key, str_value)

    str_key = '"p_sd_date"'
    str_value = str_p_sd_date
    req_item.append(class_req())
    req_item[-1].add_data(str_key, str_value)
    
    # API request区分
    str_key = '"sCLMID"'
    str_value = 'CLMMfdsGetMarketPriceHistory'  # 蓄積情報問合取得を指示。
    req_item.append(class_req())
    req_item[-1].add_data(str_key, str_value)

    # 銘柄コード     通常銘柄、4桁。優先株等、5桁。例、伊藤園'2593'、伊藤園優先株'25935'
    str_key = '"sIssueCode"'
    str_value = str_sIssueCode
    req_item.append(class_req())
    req_item[-1].add_data(str_key, str_value)
    
    # 市場C   対象の市場コード（現在"00":東証のみ）、引数省略可能（デフォルト＝東証）。
    str_key = '"sSizyouC"'
    str_value = str_sSizyouC
    req_item.append(class_req())
    req_item[-1].add_data(str_key, str_value)


    # 返り値の表示形式指定
    str_key = '"sJsonOfmt"'
    str_value = class_cust_property.sJsonOfmt    # "5"は "1"（ビット目ＯＮ）と"4"（ビット目ＯＮ）の指定となり「ブラウザで見や易い形式」且つ「引数項目名称」で応答を返す値指定
    req_item.append(class_req())
    req_item[-1].add_data(str_key, str_value)

    # URL文字列の作成
    str_url = func_make_url_request(False, \
                                     class_cust_property.sUrlPrice, \
                                     req_item)
    # API問合せ
    json_return = func_api_req(str_url)

    price_history = json_return.get('aCLMMfdsMarketPriceHistory')
    if price_history:
        total_days = len(price_history)
        date_range = None
        if total_days > 0:
            oldest_date = price_history[-1]['sDate']
            newest_date = price_history[0]['sDate']
            date_range = f"期間: {oldest_date} ～ {newest_date}"
        
        # グローバルなロガーを使用
        logger = logging.getLogger()
        logger.info(f"取得した価格履歴数: {total_days}日分 {date_range if date_range else ''}")

    return json_return



# 機能: タイトル行を株価情報のファイルに書き込む
# 引数1: 出力ファイル名
# 備考: 指定ファイルを開き、１行目に項目コード、２行目に項目名を書き込む。
def func_write_daily_price_title(str_fname_output):
    try:
        with open(str_fname_output, 'w', encoding = 'shift_jis') as fout:
            print('file open at w, "fout": ', str_fname_output )
            # 項目コード
            str_text_out = ''
            str_text_out = str_text_out + 'sDate' + ','
            str_text_out = str_text_out + 'pDOP' + ','
            str_text_out = str_text_out + 'pDHP' + ','
            str_text_out = str_text_out + 'pDLP' + ','
            str_text_out = str_text_out + 'pDPP' + ','
            str_text_out = str_text_out + 'pDV' + ','
            str_text_out = str_text_out + 'pDOPxK' + ','
            str_text_out = str_text_out + 'pDHPxK' + ','
            str_text_out = str_text_out + 'pDLPxK' + ','
            str_text_out = str_text_out + 'pDPPxK' + ','
            str_text_out = str_text_out + 'pDVxK' + ','
            str_text_out = str_text_out + 'pSPUO' + ','
            str_text_out = str_text_out + 'pSPUC' + ','
            str_text_out = str_text_out + 'pSPUK' + '\n'
            fout.write(str_text_out)     # １行目に列名を書き込む

            # 項目名
            str_text_out = ''
            str_text_out = str_text_out + '日付（YYYYMMDD）' + ','
            str_text_out = str_text_out + '始値' + ','
            str_text_out = str_text_out + '高値' + ','
            str_text_out = str_text_out + '安値' + ','
            str_text_out = str_text_out + '終値' + ','
            str_text_out = str_text_out + '出来高' + ','
            str_text_out = str_text_out + '始値（分割調整済み）' + ','
            str_text_out = str_text_out + '高値（分割調整済み）' + ','
            str_text_out = str_text_out + '安値（分割調整済み）' + ','
            str_text_out = str_text_out + '終値（分割調整済み）' + ','
            str_text_out = str_text_out + '出来高（分割調整済み）' + ','
            str_text_out = str_text_out + '株式分割前単位' + ','
            str_text_out = str_text_out + '株式分割後単位' + ','
            str_text_out = str_text_out + '株式分割換算係数（pSPUO/pSPUC）' + '\n'
            fout.write(str_text_out)     # １行目に列名を書き込む

    except IOError as e:
        print('Can not Write!!!')
        print(type(e))


# 機能: 取得した株価情報を追記モードでファイルに書き込む
# 引数1: 出力ファイル名
# 引数2: 取得した株価情報（リスト型）
# 備考:
#   指定ファイルを開き、1〜2行目に取得する情報名を書き込み、3行目以降で取得した情報を書き込む。
#   pSPUO,pSPUC,pSPUK は株式分割日（権利落ち日)のみデータが返る。通常は項目自体返らない。
def func_write_daily_price(str_fname_output, list_return):
    try:
        with open(str_fname_output, 'a', encoding = 'shift_jis') as fout:
            print('file open at a, "fout": ', str_fname_output )
            # 取得した情報から行データを作成し書き込む
            str_text_out = ''
            
            # 日足データを取得できた場合。
            if list_return != None :
                for i in range(len(list_return)):
                    # 行データ作成
                    str_text_out = list_return[i].get("sDate")
                    str_text_out = str_text_out + ',' + list_return[i].get("pDOP")
                    str_text_out = str_text_out + ',' + list_return[i].get("pDHP")
                    str_text_out = str_text_out + ',' + list_return[i].get("pDLP")
                    str_text_out = str_text_out + ',' + list_return[i].get("pDPP")
                    str_text_out = str_text_out + ',' + list_return[i].get("pDV")
                    str_text_out = str_text_out + ',' + list_return[i].get("pDOPxK")
                    str_text_out = str_text_out + ',' + list_return[i].get("pDHPxK")
                    str_text_out = str_text_out + ',' + list_return[i].get("pDLPxK")
                    str_text_out = str_text_out + ',' + list_return[i].get("pDPPxK")
                    str_text_out = str_text_out + ',' + list_return[i].get("pDVxK")
                    # pSPUO,pSPUC,pSPUK は株式分割日（権利落ち日)のみ設定される。
                    if not list_return[i].get("pSPUO") ==  None:
                        str_text_out = str_text_out + ',' + list_return[i].get("pSPUO")
                        str_text_out = str_text_out + ',' + list_return[i].get("pSPUC")
                        str_text_out = str_text_out + ',' + list_return[i].get("pSPUK")
                    str_text_out = str_text_out + '\n'

                    fout.write(str_text_out)     # 処理済みの株価データをファイルに書き込む
                    
            # 日足データを取得できない場合。
            else :
                str_text_out = '日足データがありません。\n'
                print(str_text_out)
                fout.write(str_text_out)     # 処理済みの株価データをファイルに書き込む


    except IOError as e:
        print('Can not Write!!!')
        print(type(e))
        



    
    
# ======================================================================================================
# ==== プログラム始点 =================================================================================
# ======================================================================================================

class RateLimiter:
    def __init__(self, max_requests, time_window, logger):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()
        self.lock = Lock()
        self.logger = logger
    
    def acquire(self):
        with self.lock:
            now = time.time()
            
            # 時間枠外のリクエストを削除
            while self.requests and self.requests[0] <= now - self.time_window:
                self.requests.popleft()
            
            # リクエスト数が上限に達している場合は待機
            if len(self.requests) >= self.max_requests:
                sleep_time = self.requests[0] - (now - self.time_window)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    now = time.time()
            
            # 新しいリクエストを記録
            self.requests.append(now)

            # 現在のリクエスト数をログ出力
            current_requests = len(self.requests)
            if current_requests >= self.max_requests:
                self.logger.debug(f"レートリミット到達: {current_requests}件のリクエスト")

class TachibanaStockAPI:
    def __init__(self, num_threads=1):
        self.logger = logging.getLogger()
        self.repo = StockRepository()
        self.num_threads = num_threads
        self.lock = threading.Lock()
        self.rate_limiter = RateLimiter(
            max_requests=8, 
            time_window=1.0,
            logger=self.logger
        )
        self.execution_mode = None
        self.stop_requested = False
        
        # シグナルハンドラを設定
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """シグナルを受け取った時の処理"""
        self.logger.warning('\n停止リクエストを受け付けました。実行中の処理が完了するまでお待ちください...')
        self.stop_requested = True

    def load_credentials(self):
        """認証情報ファイルから設定を読み込む"""
        credentials = {}
        try:
            with open('.tachibana_credentials', 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        credentials[key.strip()] = value.strip()
            
            # 実行モードの取得（デフォルトはfull）
            self.execution_mode = credentials.get('EXECUTION_MODE', 'full').lower()
            if self.execution_mode not in ['daily', 'full']:
                self.logger.warning(f"無効な実行モード: {self.execution_mode}、デフォルトの'full'を使用します")
                self.execution_mode = 'full'
                
        except FileNotFoundError:
            raise FileNotFoundError(
                "認証情報ファイル(.tachibana_credentials)が見つかりません。"
                "以下の形式でファイルを作成してください:\n"
                "TACHIBANA_API_URL=https://demo-kabuka.e-shiten.jp/e_api_v4r6/\n"
                "TACHIBANA_USER_ID=your_user_id\n"
                "TACHIBANA_PASSWORD=your_password\n"
                "TACHIBANA_SECOND_PASSWORD=your_second_password\n"
                "EXECUTION_MODE=daily  # または full"
            )
        return credentials

    def get_stock_codes(self):
        codes = self.repo.fetch_company_code_list()
        self.logger.debug(f"DBから取得した銘柄コード一覧: {codes}")
        # APIで使用する4桁コードに変換
        formatted_codes = []
        for code in codes:
            if len(code) == 5:
                # 末尾の0を削除して4桁に
                formatted_codes.append(code[:-1])
            else:
                self.logger.warning(f"不正な長さの銘柄コード: {code}")
                continue
        
        return formatted_codes

    def process_stock_code(self, code, class_cust_property, int_p_no):
        # 停止フラグのチェックを追加
        if self.stop_requested:
            return  # ログ出力なしで静かにスキップ

        try:
            self.logger.debug(f"処理開始: コード={code}")
            self.logger.info(f'銘柄コード {code} の株価データを取得します')
            
            # 業種名を取得（DBに格納されている形式の5桁コードを使用）
            code_5digit = code + "0" if len(code) == 4 else code  # 既に5桁の場合はそのまま
            try:
                industry_name = self.repo.fetch_industry_name_prefix(code_5digit)
                if not industry_name:
                    self.logger.warning(f'銘柄コード {code}（5桁：{code_5digit}）の業種名が取得できませんでした。スキップします。')
                    return
            except Exception as e:
                self.logger.error(f'業種名取得エラー（コード：{code}、5桁：{code_5digit}）: {str(e)}')
                return
            
            self.logger.info(f'銘柄コード {code} の業種名: {industry_name}')
            
            # 株価データ取得用のパラメータを設定
            my_sIssueCode = code
            my_sSizyouC = '00'
            
            # レートリミッターを使用
            self.rate_limiter.acquire()
            
            with self.lock:
                # 株価データを取得
                dic_return = func_get_daily_price(int_p_no, my_sIssueCode, my_sSizyouC, class_cust_property)
                self.logger.debug(f"API応答: {dic_return}")  # APIからの応答全体を確認
            
            # 日足株価部分をリスト型で抜き出す
            price_history = dic_return.get('aCLMMfdsMarketPriceHistory')
            
            # 成功フラグを初期化
            success = False
            
            if price_history:
                self.logger.debug(f"取得した価格履歴数: {len(price_history)}")
                if self.execution_mode == 'daily':
                    self.logger.debug(f"最新の日付: {price_history[0]['sDate']}")
                
                self.logger.info(f'銘柄コード {code} の株価データをDBに保存します')
                
                # dailyモードの場合、直近5営業日のデータのみを処理
                if self.execution_mode == 'daily':
                    price_history = sorted(price_history, key=lambda x: x['sDate'], reverse=True)[:5]
                
                # 日毎のデータをDBに保存
                for daily_price in price_history:
                    try:
                        # 日付形式を変換（'YYYYMMDD' → 'YYYY-MM-DD'）
                        date_str = daily_price['sDate']
                        formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                        
                        # 株価データを整形（4桁コードを使用）
                        price_data = {
                            'code': code,  # 4桁コードをそのまま使用
                            'date': formatted_date,
                            'open': float(daily_price['pDOP']),
                            'high': float(daily_price['pDHP']),
                            'low': float(daily_price['pDLP']),
                            'close': float(daily_price['pDPP']),
                            'volume': int(daily_price['pDV'])
                        }
                        
                        # DBに保存を試みる前にログ出力を追加
                        self.logger.debug(f"保存するデータ: {price_data}")
                        
                        # DBに保存（industry_nameと4桁コードを使用）
                        current_success = self.repo.insert_stock_price_data(price_data, industry_name)
                        if not current_success:
                            self.logger.warning(f"日付 {formatted_date} のデータ保存に失敗しました")
                        else:
                            self.logger.debug(f"日付 {formatted_date} のデータを保存しました")
                            success = True  # 少なくとも1件のデータが保存できれば成功とみなす
                        
                    except Exception as e:
                        self.logger.error(f"データ保存中にエラーが発生しました: {str(e)}")
                        continue
                
                self.logger.info(f'銘柄コード {code} の株価データの保存が完了しました')
            else:
                self.logger.warning(f'銘柄コード {code} の株価データが取得できませんでした')
            
            if success:  # 株価データの保存が成功した場合
                # インジケーター計算・保存を実行
                indicator_success = self.calculate_and_save_indicators(code, industry_name)
                if indicator_success:
                    self.logger.info(f"銘柄コード {code} の全処理が完了しました")
            
        except Exception as e:
            self.logger.error(f'銘柄コード {code} の処理中にエラーが発生しました: {str(e)}')

    def execute_stock_price_retrieval(self, start_code=None):
        """株価データ取得処理を実行します"""
        from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
        import threading

        # 停止フラグを初期化
        self.stop_requested = False

        # 認証情報を読み込む
        credentials = self.load_credentials()

        # 接続先設定
        my_url = credentials['TACHIBANA_API_URL']
        my_userid = credentials['TACHIBANA_USER_ID']
        my_passwd = credentials['TACHIBANA_PASSWORD']
        my_2pwd = credentials['TACHIBANA_SECOND_PASSWORD']

        class_cust_property = class_def_cust_property()

        # ID、パスワード、第２パスワードのURLエンコード
        my_userid = func_replace_urlecnode(my_userid)
        my_passwd = func_replace_urlecnode(my_passwd)
        class_cust_property.sSecondPassword = func_replace_urlecnode(my_2pwd)
        class_cust_property.sJsonOfmt = '5'

        self.logger.info('立花証券APIにログインします')
        int_p_no = 1
        bool_login = func_login(int_p_no, my_url, my_userid, my_passwd, class_cust_property)

        if not bool_login:
            self.logger.error('ログインに失敗しました')
            return

        try:
            self.logger.info(f'株価データの取得を開始します（実行モード: {self.execution_mode}）')
            
            stock_codes = self.get_stock_codes()
            
            if start_code:
                try:
                    start_index = stock_codes.index(start_code)
                    stock_codes = stock_codes[start_index:]
                    self.logger.info(f'銘柄コード {start_code} から処理を開始します')
                except ValueError:
                    self.logger.warning(f'指定された銘柄コード {start_code} が見つかりません。最初から処理を開始します')
            
            total_codes = len(stock_codes)
            self.logger.info(f'処理対象銘柄数: {total_codes}')
            self.logger.info(f'使用スレッド数: {self.num_threads}')

            with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                futures = []
                completed_count = 0

                # 銘柄コードを処理
                for idx, code in enumerate(stock_codes, 1):
                    if self.stop_requested:
                        break  # 静かに処理を中断

                    future = executor.submit(
                        self.process_stock_code,
                        code,
                        class_cust_property,
                        idx + 1
                    )
                    futures.append(future)

                # 実行中のタスクの完了を待機
                while futures and not self.stop_requested:
                    # 完了したタスクを確認
                    done, futures = wait(futures, return_when=FIRST_COMPLETED)
                    
                    for future in done:
                        try:
                            future.result()
                            completed_count += 1
                            self.logger.info(f'進捗: {completed_count}/{total_codes} ({(completed_count/total_codes*100):.1f}%)')
                        except Exception as e:
                            self.logger.error(f'タスク実行中にエラーが発生しました: {str(e)}')

                if self.stop_requested:
                    # 実行中のタスクの完了を待機（ログ出力なし）
                    for future in futures:
                        try:
                            future.result()
                        except Exception as e:
                            self.logger.error(f'タスク実行中にエラーが発生しました: {str(e)}')

        except Exception as e:
            self.logger.error(f"エラーが発生しました: {str(e)}")
            raise
        
        finally:
            # ログアウト処理
            try:
                self.logger.info('\nログアウトを実行します')
                int_p_no = total_codes + 2
                bool_logout = func_logout(int_p_no, class_cust_property)
                if bool_logout:
                    self.logger.info('ログアウトに成功しました')
                else:
                    self.logger.error('ログアウトに失敗しました')
            except Exception as e:
                self.logger.error(f'ログアウト中にエラーが発生しました: {str(e)}')

    def calculate_and_save_indicators(self, code: str, industry_name: str):
        """株価データを取得してインジケーターを計算・保存"""
        try:
            # DBから株価データを取得（最新100営業日分）
            price_data = self.repo.fetch_stock_prices(code, industry_name, limit=100)
            
            if not price_data:
                self.logger.warning(f"銘柄コード {code} の株価データが見つかりません")
                return False
            
            self.logger.info(f"銘柄コード {code} のインジケーター計算を開始します（データ数: {len(price_data)}日分）")
            
            # 日付でソート（古い順）
            price_data = sorted(price_data, key=lambda x: x['date'])
            
            # インジケーター計算（デイリー処理用の軽量版）
            from service.indicator_service import IndicatorService
            indicator_service = IndicatorService(self.repo)
            
            # 直近5日分のインジケーターのみを計算・保存する
            success = indicator_service.calculate_latest_indicators(price_data, code, industry_name, latest_days=5)
            
            if success:
                self.logger.info(f"銘柄コード {code} のインジケーター計算・保存が完了しました")
                
                # 最新のインジケーターの値をログに出力
                try:
                    # 最新の1件だけを取得
                    indicators = self.repo.fetch_latest_indicators(code, industry_name)
                    if indicators:
                        latest = indicators[0]  # 最新の1件
                        self.logger.info(f"最新のインジケーター値（{latest['date']}）:")
                        self.logger.info(f"  一目均衡表: 転換線={format(latest['ichimoku_tenkan'], '.2f') if latest['ichimoku_tenkan'] is not None else 'None'}, 基準線={format(latest['ichimoku_kijun'], '.2f') if latest['ichimoku_kijun'] is not None else 'None'}")
                        self.logger.info(f"  ボリンジャーバンド: 上限={format(latest['bb_upper'], '.2f') if latest['bb_upper'] is not None else 'None'}, 中央={format(latest['bb_middle'], '.2f') if latest['bb_middle'] is not None else 'None'}, 下限={format(latest['bb_lower'], '.2f') if latest['bb_lower'] is not None else 'None'}")
                        self.logger.info(f"  RSI: {format(latest['rsi'], '.2f') if latest['rsi'] is not None else 'None'}, MACD: {format(latest['macd'], '.2f') if latest['macd'] is not None else 'None'}")
                except Exception as e:
                    self.logger.error(f"最新インジケーター値の取得エラー: {str(e)}")
                
                return success
            
            self.logger.warning(f"銘柄コード {code} のインジケーター計算結果が空です")
            return False
            
        except Exception as e:
            self.logger.error(f"インジケーター計算中にエラーが発生しました: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False