import pytest
import main
import utils.grc_price_utils as grc_price_utils
from typing import Dict,List,Tuple,Union,Any
# Tests that require a network connection and will fail without one
APPROVED_PROJECT_URLS={}

@pytest.fixture()
def test_get_approved_project_urls_web():
    """
    This test only tests network functionality. Test of parsing etc is found in a similar test in main tests
    @return:
    """
    global APPROVED_PROJECT_URLS
    APPROVED_PROJECT_URLS=main.get_approved_project_urls_web()


def test_get_project_mag_ratios_from_url(test_get_approved_project_urls_web):
    result=main.get_project_mag_ratios_from_url(30,APPROVED_PROJECT_URLS)
    assert len(result)>3


def test_get_grc_price():
    # Function to test the soup finds for getting the grc price. Note this may fail if you get a "are you a bot?" page.
    # Inspect the html before assuming that the finds are broken.
    price, _, _, _, _ = grc_price_utils.get_grc_price_from_sites()

    assert price
    assert isinstance(price,float)


def test_grc_grc_price():
    answer=main.get_grc_price()
    assert isinstance(answer,float)