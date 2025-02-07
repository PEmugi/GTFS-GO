import json

# QGIS-API
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtNetwork import QNetworkRequest, QNetworkReply
from qgis.core import *
from qgis.gui import *
from qgis.utils import iface

DPF_API_URL = "https://api.gtfs-data.jp/gtfs"


def fetch(url: str) -> dict:
    """
    Fetch data via http in QGIS-manner
    reponse must be  JSON-text

    Args:
        url (str): [description]

    Raises:
        Exception: [description]

    Returns:
        dict: decode JSON-text as python-dictionary
    """
    eventLoop = QEventLoop()
    networkAccessManager = QgsNetworkAccessManager.instance()
    req = QNetworkRequest(QUrl(url))
    reply = networkAccessManager.get(req)
    reply.finished.connect(eventLoop.quit)
    eventLoop.exec_()
    if reply.error() == QNetworkReply.NoError:
        text_stream = QTextStream(reply)
        text_stream.setCodec("UTF-8")
        text = text_stream.readAll()
        return json.loads(text)
    else:
        raise Exception(reply.error())


def get_feeds(target_date: str, extent=None, pref=None):
    url = DPF_API_URL + "/findByAttributes?"
    url += f"target_date={target_date}"
    url += "" if extent is None else "&extent=" + extent
    url += "" if pref is None else "&pref=" + pref

    res = fetch(url)
    feeds = res.get("data", [])
    return feeds
