import requests
from urllib.parse import urlencode, unquote
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
import re
import json
from lxml import etree
import datetime
from io import BytesIO
from keras.models import load_model
import numpy as np
import os
from PIL import Image, ImageOps


class Baidu(object):
    def __init__(self):
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        self.driver = webdriver.Chrome(chrome_options=chrome_options)

    def login(self, username, password):
        pass

    def parse(self, image):
        y = self.model.predict(image)
        y = y.argsort()[:, -1]
        y = ''.join(list(map(lambda x: ',' if x == 10 else str(x), y)))
        return y

    def load_model(self):
        self.model = load_model('model/model.h5')

    def bootstrap(self):
        cookie_file = open('baidu.cookie', 'r')
        cookies = json.load(cookie_file)
        base_dir = os.path.abspath(os.path.dirname(__file__))
        self.driver.get('http://index.baidu.com')
        for ele in cookies:
            self.driver.add_cookie(ele)
        self.headers = {
            'Cookie':
            ';'.join(
                '{}={}'.format(ele['name'], ele['value']) for ele in cookies),
            'User-Agent':
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36',
        }
        with open('%s/raphael.js' % base_dir, 'r') as f:
            self.driver.execute_script(f.read())
        self.js_template = """
        document.getElementsByClassName('view-value')[0].innerHTML = '%s'
        """

    def main(self, keyword, start, end):
        self.bootstrap()
        url_args = {'tpl': 'trend', 'word': keyword.encode('gbk')}
        url = 'http://index.baidu.com/?' + urlencode(url_args)
        text = self.get(url)
        res1 = self.get_res1(text)
        res2 = self.get_res2(text)
        res3_datas = self.get_res3(res1, res2, start, end)
        for ele in res3_datas:
            res3 = ele['res3']
            date = ele['date']
            trend = self.get_index(res1, res2, res3)
            print({'date': date, 'trend': trend})

    def get(self, url, binary=False):
        res = requests.get(url, headers=self.headers)
        if binary:
            return res.content
        else:
            return res.text
        return requests.get(url).text.replace('\r', '')

    def get_index(self, res1, res2, res3):
        url_args = {
            'res': res1,
            'res2': res2,
            'res3[]': res3,
        }
        url = 'http://index.baidu.com/Interface/IndexShow/show/?' + urlencode(
            url_args)
        data = self.get(url)
        datas = json.loads(data)
        html_code = datas['data']['code'][0]
        img_url = re.search(r'url\((".*?")\)}', html_code)[1]
        res = self.get(
            'http://index.baidu.com' + img_url.replace('"', ''), binary=True)
        img = Image.open(BytesIO(res))
        img = img.convert('L')
        img = ImageOps.invert(img)
        arr = np.array(img)
        arr[arr > 100] = 255
        arr[arr < 100] = 0
        tmp = []
        doc = etree.HTML('<html>{}</html>'.format(html_code))
        values = doc.xpath('//span[@class="imgval"]')
        for ele in values:
            width = ele.get('style')
            margin = ele.xpath('./div')[0].get('style')
            width = re.findall(r'\d+', width)[0]
            margin = re.findall(r'\d+', margin)[0]
            margin, width = int(margin), int(width)
            roi = arr[:, margin:margin + width]
            tmp.append(roi)
        merge = np.hstack(tmp)
        width = merge.shape[1]
        split_numbers = width / 8
        lst = np.hsplit(merge, split_numbers)
        lst = np.array(list(map(lambda x: x.reshape((14, 8, 1)), lst)))
        y = self.parse(lst)
        return y

    def get_res3(self, res1, res2, start, end):
        url_args = {
            'res': res1,
            'res2': res2,
            'startdate': start,
            'enddate': end,
        }
        url = 'http://index.baidu.com/Interface/Search/getSubIndex/?' + urlencode(
            url_args)
        html = self.get(url)
        datas = json.loads(html)
        res3_list = datas['data']['all'][0]['userIndexes_enc'].split(',')
        res3_datas = []
        cur_date = datetime.datetime.strptime(start, '%Y-%m-%d')
        for res3 in res3_list:
            res3_datas.append({
                'res3': res3,
                'date': cur_date.strftime('%Y-%m-%d')
            })
            cur_date += datetime.timedelta(days=1)
        return res3_datas

    def get_res1(self, text):
        """
            get res1, parse html to get res1.
        """
        res = re.search(r'.*PPval\.ppt = \'(.*?)\'', text)
        res = unquote(res[1]) if res else None
        return res

    def get_res2(self, text):
        """
        这段是抄的 大该意思是提取func 使用selenium执行
        """
        doc = etree.HTML(text)
        script_block = doc.xpath(
            '//script[contains(text(),"res2")]/text()')[0].replace('\r', '')
        res_script_list = script_block.split('\n')
        first_var = re.search(r'(.{15}) = \'.{50}\';',
                              script_block)[1].lstrip(' ')
        all_var = []
        all_var.append(first_var)
        final_script_list = []
        res_var = None
        for line in res_script_list:
            if res_var:
                break
            for var in all_var:
                if var in line:
                    temp_var = re.search(r'(.*?) = .*?', line)
                    if temp_var:
                        temp_var = temp_var[1].lstrip(' ')
                        all_var.append(temp_var)
                        final_script_list.append(line.strip(' '))
                    else:
                        res_var = line.lstrip(' ').rstrip(');').replace(
                            'BID.res2(', '')
                    break
        final_script = '\n'.join(final_script_list)
        res_script = """
        function %s_func () {
            %s
            return %s
        }
        return %s_func()
        """ % (res_var, final_script, res_var, res_var)
        result = self.driver.execute_script(res_script)
        return result


def main():
    bd = Baidu()
    bd.load_model()
    bd.main('btc', '2018-10-01', '2018-10-08')


if __name__ == '__main__':
    main()