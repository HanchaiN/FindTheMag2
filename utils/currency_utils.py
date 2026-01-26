from __future__ import annotations

import random
from typing import Union, Dict, List, Tuple

import requests

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
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36",
)

CURRENCY_URLS = ("https://currencyrateapi.com/api/latest?codes={code}&base_currency=USD",)


def parse_currency_soup(
    url: str, response: requests.Response
) -> Tuple[Union[float, None], str, str]:
    float_price = None
    info_message = ""
    url_message = ""

    if url.startswith("https://currencyrateapi.com/api/"):
        data = None
        try:
            data = response.json()
        except Exception:
            pass
        if data is not None and "result" in data and len(data["result"]) == 1:
            float_price = float(next(iter(data["result"].values())))
            info_message = f"Found exchange rate of {float_price} per USD from {url}"
        else:
            url_message = f"Error getting info from {url}"

    return float_price, url_message, info_message


def get_currency_from_sites(
    currency_code: str,
    proxies: Union[Dict[str, str]] = None
) -> Tuple[Union[float, None], str, List[str], List[str], List[str]]:
    if currency_code == "USD":
        return (
            1,
            "Fixed exchange rate of 1 USD per USD",
            ["Fixed exchange rate of 1 per USD"],
            [""],
            [""],
        )
    headers = requests.utils.default_headers()
    headers["User-Agent"] = random.choice(AGENTS)
    found_prices = []
    url_messages = []
    info_logger_messages = []
    error_logger_messages = []

    for url_ in CURRENCY_URLS:
        url = url_.format(code=currency_code)
        try:
            response = requests.get(url, headers=headers, timeout=5, proxies=proxies)
        except requests.exceptions.Timeout as error:
            error_logger_messages.append(f"Error fetching stats from {url}: {error}")
            continue

        price, url_message, info_message = parse_currency_soup(url, response)

        if price is not None:
            found_prices.append(price)

        url_messages.append(url_message)
        info_logger_messages.append(info_message)

    if len(found_prices) > 0:
        avg_rate = sum(found_prices) / len(found_prices)
        table_message = (
            f"Found currency exchange rate {avg_rate} {currency_code} per USD"
        )
        return (
            avg_rate,
            table_message,
            url_messages,
            info_logger_messages,
            error_logger_messages,
        )

    table_message = "Unable to find GRC price"
    return (
        None,
        table_message,
        url_messages,
        info_logger_messages,
        error_logger_messages,
    )
