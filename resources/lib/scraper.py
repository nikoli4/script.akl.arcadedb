# -*- coding: utf-8 -*-
#
# Advanced Kodi Launcher scraping engine for ArcadeDB.

# Copyright (c) 2020-2021 Chrisism
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.

# --- Python standard library ---
from __future__ import unicode_literals
from __future__ import division

import logging
import json

# --- AKL packages ---
from akl import constants, settings
from akl.utils import net
from akl.scrapers import Scraper
from akl.api import ROMObj

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------------------------------
# Arcade Database online scraper (for MAME).
# Implementation logic of this scraper is very similar to ScreenScraper.
#
# | Site     | https://adb.arcadeitalia.net/                    |
# | API info | https://adb.arcadeitalia.net/service_scraper.php |
# -------------------------------------------------------------------------------------------------
class ArcadeDB(Scraper):
    # --- Class variables ------------------------------------------------------------------------
    supported_metadata_list = [
        constants.META_TITLE_ID,
        constants.META_YEAR_ID,
        constants.META_GENRE_ID,
        constants.META_DEVELOPER_ID,
        constants.META_NPLAYERS_ID,
        constants.META_PLOT_ID,
    ]
    supported_asset_list = [
        constants.ASSET_TITLE_ID,
        constants.ASSET_SNAP_ID,
        constants.ASSET_BOXFRONT_ID,
        constants.ASSET_FLYER_ID,
    ]

    # --- Constructor ----------------------------------------------------------------------------
    def __init__(self):
        # --- Misc stuff ---
        self.cache_candidates = {}
        self.cache_metadata = {}
        self.cache_assets = {}
        self.all_asset_cache = {}
        
        cache_dir = settings.getSettingAsFilePath('scraper_cache_dir')
        super(ArcadeDB, self).__init__(cache_dir)

    # --- Base class abstract methods ------------------------------------------------------------    
    def get_name(self): return 'ArcadeDB'

    def get_filename(self): return 'ADB'

    def supports_disk_cache(self): return True

    def supports_search_string(self): return False

    def supports_metadata_ID(self, metadata_ID):
        return True if metadata_ID in ArcadeDB.supported_metadata_list else False

    def supports_metadata(self): return True

    def supports_asset_ID(self, asset_ID):
        return True if asset_ID in ArcadeDB.supported_asset_list else False

    def supports_assets(self): return True
            
    # ArcadeDB does not require any API keys.
    def check_before_scraping(self, status_dic): return status_dic

    # Search term is always None for this scraper.
    def get_candidates(self, search_term:str, rom:ROMObj, platform, status_dic):
        # --- If scraper is disabled return immediately and silently ---
        if self.scraper_disabled:
            # If the scraper is disabled return None and do not mark error in status_dic.
            logger.debug('ArcadeDB.get_candidates() Scraper disabled. Returning empty data.')
            return None

        # Prepare data for scraping.
        rom_identifier = rom.get_identifier()

        # --- Request is not cached. Get candidates and introduce in the cache ---
        # ArcadeDB QUERY_MAME returns absolutely everything about a single ROM, including
        # metadata, artwork, etc. This data must be cached in this object for every request done.
        # See ScreenScraper comments for more info about the implementation.
        # logger.debug('ArcadeDB.get_candidates() search_term   "{0}"'.format(search_term))
        # logger.debug('ArcadeDB.get_candidates() rombase       "{0}"'.format(rombase))
        logger.debug('ArcadeDB.get_candidates() rom identifier "{0}"'.format(rom_identifier))
        logger.debug('ArcadeDB.get_candidates() AKL platform   "{0}"'.format(platform))
        json_response_dic = self._get_QUERY_MAME(rom_identifier, platform, status_dic)
        if not status_dic['status']: return None

        # --- Return cadidate list ---
        num_games = len(json_response_dic['result'])
        candidate_list = []
        if num_games == 0:
            logger.debug('ArcadeDB.get_candidates() Scraper found no game.')
        elif num_games == 1:
            logger.debug('ArcadeDB.get_candidates() Scraper found one game.')
            gameinfo_dic = json_response_dic['result'][0]
            candidate = self._new_candidate_dic()
            candidate['id'] = rom_identifier
            candidate['display_name'] = gameinfo_dic['title']
            candidate['platform'] = platform
            candidate['scraper_platform'] = platform
            candidate['order'] = 1
            candidate_list.append(candidate)

            # --- Add candidate games to the cache ---
            logger.debug('ArcadeDB.get_candidates() Adding to internal cache "{}"'.format(
                self.cache_key))
            self._update_disk_cache(Scraper.CACHE_INTERNAL, self.cache_key, json_response_dic)
        else:
            raise ValueError('Unexpected number of games returned (more than one).')

        return candidate_list

    def get_metadata(self, status_dic):
        # --- If scraper is disabled return immediately and silently ---
        if self.scraper_disabled:
            logger.debug('ArcadeDB.get_metadata() Scraper disabled. Returning empty data.')
            return self._new_gamedata_dic()

        # --- Retrieve json_response_dic from internal cache ---
        if self._check_disk_cache(Scraper.CACHE_INTERNAL, self.cache_key):
            logger.debug('ArcadeDB.get_metadata() Internal cache hit "{0}"'.format(self.cache_key))
            json_response_dic = self._retrieve_from_disk_cache(Scraper.CACHE_INTERNAL, self.cache_key)
        else:
            raise ValueError('Logic error')

        # --- Parse game metadata ---
        gameinfo_dic = json_response_dic['result'][0]
        gamedata = self._new_gamedata_dic()
        gamedata['title']     = gameinfo_dic['title']
        gamedata['year']      = gameinfo_dic['year']
        gamedata['genre']     = gameinfo_dic['genre']
        gamedata['developer'] = gameinfo_dic['manufacturer']
        gamedata['nplayers']  = str(gameinfo_dic['players'])
        gamedata['esrb']      = constants.DEFAULT_META_ESRB
        gamedata['plot']      = gameinfo_dic['history']

        return gamedata

    def get_assets(self, asset_info_id, status_dic):
        # --- If scraper is disabled return immediately and silently ---
        if self.scraper_disabled:
            logger.debug('ArcadeDB.get_assets() Scraper disabled. Returning empty data.')
            return []

        logger.debug('ArcadeDB.get_assets() Getting assets {}for candidate ID "{}"'.format(
            asset_info_id, self.candidate['id']))

        # --- Retrieve json_response_dic from internal cache ---
        if self._check_disk_cache(Scraper.CACHE_INTERNAL, self.cache_key):
            logger.debug('ArcadeDB.get_assets() Internal cache hit "{0}"'.format(self.cache_key))
            json_response_dic = self._retrieve_from_disk_cache(Scraper.CACHE_INTERNAL, self.cache_key)
        else:
            raise ValueError('Logic error')

        # --- Parse game assets ---
        gameinfo_dic = json_response_dic['result'][0]
        all_asset_list = self._retrieve_all_assets(gameinfo_dic, status_dic)
        if not status_dic['status']: return None
        asset_list = [asset_dic for asset_dic in all_asset_list if asset_dic['asset_ID'] == asset_info_id]
        logger.debug('ArcadeDB.get_assets() Total assets {0} / Returned assets {1}'.format(
            len(all_asset_list), len(asset_list)))

        return asset_list

    def resolve_asset_URL(self, selected_asset, status_dic):
        url = selected_asset['url']
        url_log = self._clean_URL_for_log(url)

        return url, url_log

    def resolve_asset_URL_extension(self, selected_asset, image_url, status_dic):
        # All ArcadeDB images are in PNG format?
        return 'png'

    # --- This class own methods -----------------------------------------------------------------
    # Plumbing function to get the cached jeu_dic dictionary returned by ScreenScraper.
    # Cache must be lazy loaded before calling this function.
    def debug_get_QUERY_MAME_dic(self, candidate):
        logger.debug('ArcadeDB.debug_get_QUERY_MAME_dic() Internal cache retrieving "{}"'.format(
            self.cache_key))
        json_response_dic = self._retrieve_from_disk_cache(Scraper.CACHE_INTERNAL, self.cache_key)

        return json_response_dic

    # Call ArcadeDB API only function to retrieve all game metadata.
    def _get_QUERY_MAME(self, rombase_noext, platform, status_dic):
        game_name = rombase_noext
        logger.debug('ArcadeDB._get_QUERY_MAME() game_name "{0}"'.format(game_name))

        # --- Build URL ---
        url_a = 'https://adb.arcadeitalia.net/service_scraper.php?ajax=query_mame'
        url_b = '&game_name={}'.format(game_name)
        url = url_a + url_b

        # --- Grab and parse URL data ---
        json_data = self._retrieve_URL_as_JSON(url, status_dic)
        if not status_dic['status']: return None
        self._dump_json_debug('ArcadeDB_get_QUERY_MAME.json', json_data)

        return json_data

    # Returns all assets found in the gameinfo_dic dictionary.
    def _retrieve_all_assets(self, gameinfo_dic, status_dic):
        all_asset_list = []

        # --- Banner (Marquee in MAME) ---
        asset_data = self._get_asset_simple(
            gameinfo_dic, constants.ASSET_BANNER_ID, 'Banner (Marquee)', 'url_image_marquee')
        if asset_data is not None: all_asset_list.append(asset_data)

        # --- Title ---
        asset_data = self._get_asset_simple(
            gameinfo_dic, constants.ASSET_TITLE_ID, 'Title screenshot', 'url_image_title')
        if asset_data is not None: all_asset_list.append(asset_data)

        # --- Snap ---
        asset_data = self._get_asset_simple(
            gameinfo_dic, constants.ASSET_SNAP_ID, 'Snap screenshot', 'url_image_ingame')
        if asset_data is not None: all_asset_list.append(asset_data)

        # --- BoxFront (Cabinet in MAME) ---
        asset_data = self._get_asset_simple(
            gameinfo_dic, constants.ASSET_BOXFRONT_ID, 'BoxFront (Cabinet)', 'url_image_cabinet')
        if asset_data is not None: all_asset_list.append(asset_data)

        # --- BoxBack (CPanel in MAME) ---
        # asset_data = self._get_asset_simple(
        #     gameinfo_dic, ASSET_BOXBACK_ID, 'BoxBack (CPanel)', '')
        # if asset_data is not None: all_asset_list.append(asset_data)

        # --- Cartridge (PCB in MAME) ---
        # asset_data = self._get_asset_simple(
        #     gameinfo_dic, ASSET_CARTRIDGE_ID, 'Cartridge (PCB)', '')
        # if asset_data is not None: all_asset_list.append(asset_data)

        # --- Flyer ---
        asset_data = self._get_asset_simple(
            gameinfo_dic, constants.ASSET_FLYER_ID, 'Flyer', 'url_image_flyer')
        if asset_data is not None: all_asset_list.append(asset_data)

        return all_asset_list
    
    def _get_asset_simple(self, data_dic, asset_ID, title_str, key):
        if key in data_dic:
            asset_data = self._new_assetdata_dic()
            asset_data['asset_ID'] = asset_ID
            asset_data['display_name'] = title_str
            asset_data['url_thumb'] = data_dic[key]
            asset_data['url'] = data_dic[key]
            return asset_data
        else:
            return None

    # No need for URL cleaning in ArcadeDB.
    def _clean_URL_for_log(self, url): return url

    # Retrieve URL and decode JSON object.
    # ArcadeDB API info https://adb.arcadeitalia.net/service_scraper.php
    #
    # * ArcadeDB has no API restrictions.
    # * When a game search is not succesfull ArcadeDB returns valid JSON with an empty list.
    def _retrieve_URL_as_JSON(self, url, status_dic):
        page_data_raw, http_code = net.get_URL(url, self._clean_URL_for_log(url))
        # self._dump_file_debug('ArcadeDB_data_raw.txt', page_data_raw)

        # --- Check HTTP error codes ---
        if http_code != 200:
            try:
                json_data = json.loads(page_data_raw)
                error_msg = json_data['message']
            except:
                error_msg = 'Unknown/unspecified error.'
            logger.error('ArcadeDB msg "{}"'.format(error_msg))
            self._handle_error(status_dic, 'HTTP code {} message "{}"'.format(http_code, error_msg))
            return None

        # If page_data_raw is None at this point is because of an exception in net_get_URL()
        # which is not urllib2.HTTPError.
        if page_data_raw is None:
            self._handle_error(status_dic, 'Network error/exception in net_get_URL()')
            return None

        # Convert data to JSON.
        try:
            json_data = json.loads(page_data_raw)
        except Exception as ex:
            self._handle_exception(ex, status_dic, 'Error decoding JSON data from ArcadeDB.')
            return None

        return json_data