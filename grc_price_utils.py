import random
from typing import Union

import requests
from bs4 import BeautifulSoup

AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.2592.113",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.2592.113"
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36"
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36"
)

GRC_PRICE_URLS = ("https://www.bybit.com/en/coin-price/gridcoin-research/", "https://coinstats.app/coins/gridcoin/", "https://marketcapof.com/crypto/gridcoin-research/")

def parse_grc_price_soup(url: str, price_soup: str) -> tuple[Union[float, None], str, str]:
    float_price = None
    info_message = ""
    url_message = ""

    soup = BeautifulSoup(price_soup, "html.parser")

    if url == "https://www.bybit.com/en/coin-price/gridcoin-research/":
        pre_price = soup.find("div", attrs={"data-cy": "coinPrice"})

        if pre_price is not None:
            try:
                price = pre_price.text.replace("$", "").strip()
                float_price = float(price)
                info_message = f"Found GRC price of {float_price} from {url}"
            except Exception:
                url_message = f"Error getting info from {url}"
        else:
            url_message = f"Error getting info from {url}"
    elif url == "https://coinstats.app/coins/gridcoin/":
        pre_price = soup.find("div", class_="CoinOverview_mainPrice__YygaC")

        if pre_price is not None:
            try:
                price = pre_price.p.text.replace("$", "").strip()
                float_price = float(price)
                info_message = f"Found GRC price of {float_price} from {url}"
            except Exception:
                url_message = f"Error getting info from {url}"
        else:
            url_message = f"Error getting info from {url}"
    elif url == "https://marketcapof.com/crypto/gridcoin-research/":
        pre_pre_price = soup.find("div", class_="price")

        if pre_pre_price is not None:
            pre_price = pre_pre_price.find(string=True, recursive=False)

            if pre_price is not None:
                try:
                    price = pre_price.replace("$", "").strip()
                    float_price = float(price)
                    info_message = f"Found GRC price of {float_price} from {url}"
                except Exception:
                    url_message = f"Error getting info from {url}"
            else:
                url_message = f"Error getting info from {url}"
        else:
            url_message = f"Error getting info from {url}"

    return float_price, url_message, info_message


def get_grc_price_from_sites() -> tuple[Union[float, None], str, list, list, list]:
    headers = requests.utils.default_headers()
    headers["User-Agent"] = random.choice(AGENTS)
    found_prices = []
    url_messages = []
    info_logger_messages = []
    error_logger_messages = []

    for url in GRC_PRICE_URLS:
        try:
            response = requests.get(url, headers=headers, timeout=5)
        except requests.exceptions.Timeout as error:
            error_logger_messages.append(f"Error fetching stats from {url}: {error}")
            continue

        price, url_message, info_message = parse_grc_price_soup(url, response.content)

        if price is not None:
            found_prices.append(price)

        url_messages.append(url_message)
        info_logger_messages.append(info_message)

    if len(found_prices) > 0:
        table_message = f"Found GRC price {sum(found_prices) / len(found_prices)}"
        return sum(found_prices) / len(found_prices), table_message, url_messages, info_logger_messages, error_logger_messages

    table_message = "Unable to find GRC price"
    return None, table_message, url_messages, info_logger_messages, error_logger_messages
