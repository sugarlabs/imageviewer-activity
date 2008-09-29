# Copyright (C) 2008, One Laptop Per Child
# Author: Sayamindu Dasgupta <sayamindu@laptop.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA


from sugar.activity import activity
import logging

from gettext import gettext as _

import sys, os
import gtk

import ImageView
import ImageViewerToolbar


class ImageViewerActivity(activity.Activity):
    def __init__(self, handle):
        activity.Activity.__init__(self, handle)

        self.zoom = None


        self.window.__unfullscreen_button_pressed = None

        self.view = ImageView.ImageViewer()

        toolbox = activity.ActivityToolbox(self)

        self._view_toolbar = ImageViewerToolbar.ViewToolbar(self.view)
        toolbox.add_toolbar(_('View'), self._view_toolbar)
        self._view_toolbar.show()


        self.set_toolbox(toolbox)
        toolbox.show()

        self._view_toolbar.connect('go-fullscreen',
                self.__view_toolbar_go_fullscreen_cb)


        vadj = gtk.Adjustment()
        hadj = gtk.Adjustment()
        self.sw = gtk.ScrolledWindow(hadj, vadj)

        self.sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.sw.add_with_viewport(self.view)

        self.set_canvas(self.sw)
        self.sw.show_all()


    def read_file(self, file_path):
        self.view.set_file_location(file_path)

        #self.zoom = int(self.metadata.get('zoom', '0'))
        #if self.zoom == 0:
        #    self.zoom = self.view.get_property('zoom')
        #else:
        #    self.view.set_zoom(self.zoom)

    #def write_file(self, file_path):
        #try:
        #    self.metadata['zoom'] = str(self.zoom)
        #except Exception, e:
        #    logging.error('write_file(): %s', e)

    def __view_toolbar_go_fullscreen_cb(self, view_toolbar):
        # Zoom to fit screen if possible
        screen = self.get_screen()
        zoom = self.view.calculate_optimal_zoom(screen.get_width(), screen.get_height())
        self.view.set_zoom(zoom)
        
        self.fullscreen()


    

