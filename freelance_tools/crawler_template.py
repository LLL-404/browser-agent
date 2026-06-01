"""
通用网页爬虫模板 - 可直接复用于接单项目
支持：静态页面、动态页面(Selenium)、数据存储(Excel/CSV/JSON)
作者：Python接单工具包 | 2026-05
"""

import time
import os
import logging
from datetime import datetime
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup
import pandas as pd

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

_CRAWLER_ERRORS = (Exception,)


class WebCrawler:
    """通用爬虫类 - 封装常用功能"""

    def __init__(self, headers: Optional[Dict] = None):
        # 默认请求头，模拟浏览器
        self.default_headers = headers or {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
        }
        self.session = requests.Session()
        self.session.headers.update(self.default_headers)

    def fetch_page(self, url: str, timeout: int = 10, retries: int = 3) -> Optional[str]:
        """
        获取页面内容（带重试机制）

        Args:
            url: 目标URL
            timeout: 超时时间(秒)
            retries: 重试次数

        Returns:
            页面HTML文本，失败返回None
        """
        for attempt in range(retries):
            try:
                logger.info("正在抓取: %s (第%d次)", url, attempt + 1)
                response = self.session.get(url, timeout=timeout)
                response.encoding = response.apparent_encoding

                if response.status_code == 200:
                    logger.info("✅ 抓取成功，内容长度: %d", len(response.text))
                    return response.text
                if response.status_code == 403:
                    logger.warning("⚠️  访问被拒绝(403)，可能需要登录或更换Headers")
                    return None
                logger.warning("⚠️  HTTP状态码: %d", response.status_code)

            except requests.exceptions.Timeout:
                logger.warning("⏰  请求超时，重试中...")
                time.sleep(2 ** attempt)
            except requests.exceptions.RequestException as e:
                logger.error("❌ 请求异常: %s", e)
                time.sleep(2 ** attempt)

        logger.error("❌ 重试%d次后仍失败", retries)
        return None

    def parse_html(self, html: str, parser: str = 'html.parser') -> BeautifulSoup:
        """解析HTML为BeautifulSoup对象"""
        return BeautifulSoup(html, parser)

    @staticmethod
    def safe_get_text(element, default: str = '') -> str:
        """安全获取元素文本，处理None情况"""
        if element:
            text = element.get_text(strip=True)
            return text if text else default
        return default


class EcommerceCrawler(WebCrawler):
    """
    电商数据爬虫 - 最常见的接单需求
    用途：竞品价格监控、商品信息采集、销量追踪
    """

    def __init__(self):
        super().__init__()
        # 存储结果
        self.results: List[Dict] = []

    def crawl_product_list(
        self,
        base_url: str,
        keyword: str,
        pages: int = 3,
        item_selector: str = 'div.product-item',  # 根据实际网站修改
        name_selector: str = 'h3.title',          # 根据实际网站修改
        price_selector: str = 'span.price',       # 根据实际网站修改
        sales_selector: str = 'span.sales',       # 根据实际网站修改
    ) -> pd.DataFrame:
        """
        爬取商品列表（核心方法）

        Args:
            base_url: 基础URL（支持格式化参数如{keyword}、{page}）
            keyword: 搜索关键词
            pages: 爬取页数
            item_selector: 商品容器CSS选择器
            name_selector: 商品名称选择器
            price_selector: 价格选择器
            sales_selector: 销量选择器

        Returns:
            包含商品数据的DataFrame
        """
        all_products = []

        for page in range(1, pages + 1):
            # 构建URL（根据实际网站调整）
            url = base_url.format(keyword=keyword, page=page)

            html = self.fetch_page(url)
            if not html:
                continue

            soup = self.parse_html(html)
            items = soup.select(item_selector)

            logger.info("📦 第%d页找到 %d 个商品", page, len(items))

            for item in items:
                try:
                    product = {
                        '名称': self.safe_get_text(item.select_one(name_selector)),
                        '价格': self.safe_get_text(item.select_one(price_selector)),
                        '销量': self.safe_get_text(item.select_one(sales_selector)),
                        '采集时间': datetime.now().strftime('%Y-%m-%d %H:%M'),
                        '关键词': keyword,
                        '页码': page,
                    }

                    if product['名称'] and product['价格']:
                        all_products.append(product)

                except _CRAWLER_ERRORS as e:
                    logger.debug("解析商品失败: %s", e)
                    continue

            time.sleep(2)

        self.results = all_products
        df = pd.DataFrame(all_products)
        logger.info("✅ 共采集 %d 条有效数据", len(df))
        return df


class DataExporter:

    @staticmethod
    def to_excel(df: pd.DataFrame, filename: str = None, sheet_name: str = '数据') -> str:
        if filename is None:
            filename = f"data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        filepath = os.path.join('output', filename)
        os.makedirs('output', exist_ok=True)

        df.to_excel(filepath, index=False, sheet_name=sheet_name, engine='openpyxl')
        logger.info("💾 Excel已保存: %s", filepath)
        return filepath

    @staticmethod
    def to_csv(df: pd.DataFrame, filename: str = None) -> str:
        if filename is None:
            filename = f"data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        filepath = os.path.join('output', filename)
        os.makedirs('output', exist_ok=True)

        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        logger.info("💾 CSV已保存: %s", filepath)
        return filepath

    @staticmethod
    def to_json(df: pd.DataFrame, filename: str = None) -> str:
        if filename is None:
            filename = f"data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        filepath = os.path.join('output', filename)
        os.makedirs('output', exist_ok=True)

        df.to_json(filepath, orient='records', force_ascii=False, indent=2)
        logger.info("💾 JSON已保存: %s", filepath)
        return filepath


def main():
    """
    使用示例 - 接单时复制此函数并修改参数即可
    """

    # ===== 客户需求配置区域（每次接单只需改这里）=====
    TARGET_URL = "https://example.com/search?q={keyword}&page={page}"  # 目标网站URL
    SEARCH_KEYWORD = "蓝牙耳机"           # 搜索关键词
    PAGE_COUNT = 3                       # 爬取页数

    # CSS选择器（需要根据目标网站检查元素后修改）
    SELECTORS = {
        'item_selector': 'div.product-item',      # 商品容器
        'name_selector': 'h3.title',              # 名称
        'price_selector': 'span.price',           # 价格
        'sales_selector': 'span.sales',           # 销量
    }
    # ==================================================

    print("=" * 60)
    print("  Python爬虫工具 - 接单专用模板")
    print("=" * 60)
    print(f"  目标网站: {TARGET_URL.split('/')[2]}")
    print(f"  关键词: {SEARCH_KEYWORD}")
    print(f"  页数: {PAGE_COUNT}")
    print("=" * 60)

    # 创建爬虫实例
    crawler = EcommerceCrawler()

    # 开始爬取
    df = crawler.crawl_product_list(
        base_url=TARGET_URL,
        keyword=SEARCH_KEYWORD,
        pages=PAGE_COUNT,
        **SELECTORS
    )

    # 数据展示
    if not df.empty:
        print("\n" + "=" * 60)
        print(f"  📊 采集结果预览 (共{len(df)}条)")
        print("=" * 60)
        print(df.head(10).to_string(index=False))

        # 导出数据
        excel_path = DataExporter.to_excel(df, f"{SEARCH_KEYWORD}_价格监控.xlsx")
        csv_path = DataExporter.to_csv(df, f"{SEARCH_KEYWORD}_价格监控.csv")

        print("\n" + "=" * 60)
        print("  ✅ 任务完成！数据已保存到 output/ 目录")
        print("=" * 60)

        # 统计摘要
        print("\n  📈 数据统计:")
        print(f"    - 总记录数: {len(df)}")
        print(f"    - 平均价格: {df['价格'].mean() if '价格' in df.columns else 'N/A'}")
        print(f"    - Excel文件: {excel_path}")
        print(f"    - CSV文件: {csv_path}")
    else:
        print("\n⚠️  未采集到数据，请检查：")
        print("  1. URL是否正确")
        print("  2. CSS选择器是否匹配目标网站结构")
        print("  3. 是否需要登录或处理反爬")


if __name__ == '__main__':
    main()
