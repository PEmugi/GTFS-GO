# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GTFSGoDockWidget
                                 A QGIS plugin
 The plugin to show routes and stops from GTFS
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2020-10-29
        git sha              : $Format:%H$
        copyright            : (C) 2020 by MIERUNE Inc.
        email                : info@mierune.co.jp
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os
import time
import json
import urllib
import shutil
import zipfile
import tempfile
import datetime

from qgis.PyQt import QtWidgets, uic
from PyQt5.QtCore import QDate
from qgis.core import *

from .gtfs_parser import GTFSParser

from .gtfs_go_renderer import Renderer
from .gtfs_go_labeling import get_labeling_for_stops
from .gtfs_go_settings import (
    STOPS_MINIMUM_VISIBLE_SCALE,
    FILENAME_ROUTES_GEOJSON,
    FILENAME_STOPS_GEOJSON,
    FILENAME_RESULT_CSV,
    LAYERNAME_ROUTES,
    LAYERNAME_STOPS
)

DATALIST_JSON_PATH = os.path.join(
    os.path.dirname(__file__), 'gtfs_go_datalist.json')

TEMP_DIR = os.path.join(tempfile.gettempdir(), 'GTFSGo')


class GTFSGoDialog(QtWidgets.QDialog):

    def __init__(self, iface):
        """Constructor."""
        super().__init__()
        self.ui = uic.loadUi(os.path.join(os.path.dirname(
            __file__), 'gtfs_go_dialog_base.ui'), self)
        with open(DATALIST_JSON_PATH) as f:
            self.datalist = json.load(f)
        self.iface = iface
        self.combobox_zip_text = self.tr('---Load local ZipFile---')
        self.init_gui()

    def init_gui(self):
        self.ui.comboBox.addItem(self.combobox_zip_text, None)
        for data in self.datalist:
            self.ui.comboBox.addItem(self.make_combobox_text(data), data)

        # set refresh event on some ui
        self.ui.comboBox.currentIndexChanged.connect(self.refresh)
        self.ui.zipFileWidget.fileChanged.connect(self.refresh)
        self.ui.outputDirFileWidget.fileChanged.connect(self.refresh)

        # change mode by radio button
        self.ui.simpleRadioButton.clicked.connect(self.refresh)
        self.ui.freqRadioButton.clicked.connect(self.refresh)

        # set today DateEdit
        now = datetime.datetime.now()
        self.ui.filterByDateDateEdit.setDate(
            QDate(now.year, now.month, now.day))

        self.refresh()

        self.ui.pushButton.clicked.connect(self.execution)

    def make_combobox_text(self, data):
        """
        parse data to combobox-text
        data-schema: {
            country: str,
            region: str,
            name: str,
            url: str
        }

        Args:
            data ([type]): [description]

        Returns:
            str: combobox-text
        """
        return '[' + data["country"] + ']' + '[' + data["region"] + ']' + data["name"]

    def download_zip(self, url: str) -> str:
        data = urllib.request.urlopen(url).read()
        download_path = os.path.join(TEMP_DIR, str(int(time.time())) + '.zip')
        with open(download_path, mode='wb') as f:
            f.write(data)

        return download_path

    def extract_zip(self, zip_path: str) -> str:
        extracted_dir = os.path.join(TEMP_DIR, 'extract')
        os.makedirs(extracted_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extracted_dir)
        return extracted_dir

    def execution(self):
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR, exist_ok=True)

        zip_src = self.get_source()
        if zip_src.startswith('http'):
            zip_path = self.download_zip(zip_src)
        else:
            zip_path = zip_src

        extracted_dir = self.extract_zip(zip_path)
        output_dir = os.path.join(
            self.outputDirFileWidget.filePath(), self.get_group_name())
        os.makedirs(output_dir, exist_ok=True)

        if self.ui.simpleRadioButton.isChecked():
            gtfs_parser = GTFSParser(extracted_dir)
            routes_geojson = {
                'type': 'FeatureCollection',
                'features': gtfs_parser.read_routes(no_shapes=self.ui.ignoreShapesCheckbox.isChecked())
            }
            stops_geojson = {
                'type': 'FeatureCollection',
                'features': gtfs_parser.read_stops(ignore_no_route=self.ui.ignoreNoRouteStopsCheckbox.isChecked())
            }
        else:
            gtfs_parser = GTFSParser(
                extracted_dir, as_frequency=True, delimiter=self.get_delimiter())

            routes_geojson = {
                'type': 'FeatureCollection',
                'features': gtfs_parser.read_route_frequency(yyyymmdd=self.get_yyyymmdd())
            }
            stops_geojson = {
                'type': 'FeatureCollection',
                'features': gtfs_parser.read_interpolated_stops()
            }
            # write stop_id conversion result csv
            gtfs_parser.dataframes['stops'][['stop_id', 'stop_name', 'similar_stop_id', 'similar_stop_name']].to_csv(os.path.join(
                output_dir, FILENAME_RESULT_CSV), index=False, encoding='cp932')

        # sometimes geojson-dict including pd.Series, is not serializable to JSON.
        def series_to_value(series):
            return series.values[0]

        with open(os.path.join(output_dir, FILENAME_ROUTES_GEOJSON), mode='w') as f:
            json.dump(routes_geojson, f, ensure_ascii=False,
                      default=lambda series: series.values[0])
        with open(os.path.join(output_dir, FILENAME_STOPS_GEOJSON), mode='w') as f:
            json.dump(stops_geojson, f, ensure_ascii=False,
                      default=lambda series: series.values[0])

        self.show_geojson(output_dir)

        self.ui.close()

    def get_yyyymmdd(self):
        if not self.ui.filterByDateCheckBox.isChecked():
            return ''
        date = self.ui.filterByDateDateEdit.date()
        yyyy = str(date.year()).zfill(4)
        mm = str(date.month()).zfill(2)
        dd = str(date.day()).zfill(2)
        return yyyy + mm + dd

    def get_delimiter(self):
        if not self.ui.delimiterCheckBox.isChecked():
            return ''
        return self.ui.delimiterLineEdit.text()

    def show_geojson(self, geojson_dir: str):
        # these geojsons will already have been generated
        stops_geojson = os.path.join(geojson_dir, FILENAME_STOPS_GEOJSON)
        routes_geojson = os.path.join(geojson_dir, FILENAME_ROUTES_GEOJSON)

        stops_vlayer = QgsVectorLayer(stops_geojson, LAYERNAME_STOPS, 'ogr')
        routes_vlayer = QgsVectorLayer(routes_geojson, LAYERNAME_ROUTES, 'ogr')

        # make and set labeling for stops
        stops_labeling = get_labeling_for_stops(
            target_field_name="stop_name" if self.ui.simpleRadioButton.isChecked() else "similar_stop_name")
        stops_vlayer.setLabelsEnabled(True)
        stops_vlayer.setLabeling(stops_labeling)

        # adjust layer visibility
        stops_vlayer.setMinimumScale(STOPS_MINIMUM_VISIBLE_SCALE)
        stops_vlayer.setScaleBasedVisibility(True)

        # make and set renderer
        stops_renderer = Renderer(stops_vlayer, 'stop_name')
        stops_vlayer.setRenderer(stops_renderer.make_renderer())

        # there are two type route renderer, normal, frequency
        if self.ui.simpleRadioButton.isChecked():
            routes_renderer = Renderer(routes_vlayer, 'route_name')
            routes_vlayer.setRenderer(routes_renderer.make_renderer())
            added_layers = [routes_vlayer, stops_vlayer]
        else:
            # frequency mode
            routes_vlayer.loadNamedStyle(os.path.join(
                os.path.dirname(__file__), 'frequency.qml'))
            csv_vlayer = QgsVectorLayer(os.path.join(
                geojson_dir, FILENAME_RESULT_CSV), 'result.csv', 'ogr')
            added_layers = [routes_vlayer, stops_vlayer, csv_vlayer]

        # add two layers as a group
        group_name = self.get_group_name()
        self.add_layers_as_group(group_name, added_layers)

        self.iface.messageBar().pushInfo(
            self.tr('finish'),
            self.tr('generated geojson files: ') + geojson_dir)
        self.ui.close()

    def get_source(self):
        if self.ui.comboBox.currentData():
            return self.ui.comboBox.currentData().get("url")
        elif self.ui.comboBox.currentData() is None and self.ui.zipFileWidget.filePath():
            return self.ui.zipFileWidget.filePath()
        else:
            return None

    def refresh(self):
        self.ui.zipFileWidget.setEnabled(
            self.ui.comboBox.currentText() == self.combobox_zip_text)
        self.ui.pushButton.setEnabled((self.get_source() is not None) and
                                      (not self.ui.outputDirFileWidget.filePath() == ''))

        self.ui.simpleFrame.setEnabled(self.ui.simpleRadioButton.isChecked())
        self.ui.freqFrame.setEnabled(self.ui.freqRadioButton.isChecked())

    def get_group_name(self):
        if self.ui.comboBox.currentData():
            return self.ui.comboBox.currentData().get("name")
        elif self.ui.comboBox.currentData() is None and self.ui.zipFileWidget.filePath():
            return os.path.basename(self.ui.zipFileWidget.filePath()).split(".")[0]
        else:
            return "no named group"

    def add_layers_as_group(self, group_name: str, layers: [QgsMapLayer]):
        """
        add layers into project as a group.
        the order of layers is reverse to layers list order.
        if layers: [layer_A, layer_B, layer_C]
        then in tree:
        - layer_C
        - layer_B
        - layer_A

        Args:
            group_name (str): [description]
            layers ([type]): [description]
        """
        root = QgsProject().instance().layerTreeRoot()
        group = root.insertGroup(0, group_name)
        group.setExpanded(True)
        for layer in layers:
            QgsProject.instance().addMapLayer(layer, False)
            group.insertLayer(0, layer)
