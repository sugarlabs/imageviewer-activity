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

import time
import sys, os
import gtk, gobject

from sugar.graphics.objectchooser import ObjectChooser

import ImageView
import ImageViewerToolbar


class ImageViewerActivity(activity.Activity):
    def __init__(self, handle):
        activity.Activity.__init__(self, handle)

        self.zoom = None
        self._close_requested = False
        self._want_document = True

        self.view = ImageView.ImageViewer()

        toolbox = activity.ActivityToolbox(self)
        self._view_toolbar = ImageViewerToolbar.ViewToolbar(self.view)
        toolbox.add_toolbar(_('View'), self._view_toolbar)
        self._view_toolbar.show()
        self.set_toolbox(toolbox)
        toolbox.show()

        self._view_toolbar.connect('go-fullscreen',
                self.__view_toolbar_go_fullscreen_cb)

        self.connect('window-state-event', 
                self.__window_state_event_cb)

        vadj = gtk.Adjustment()
        hadj = gtk.Adjustment()
        self.sw = gtk.ScrolledWindow(hadj, vadj)

        self.sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.sw.add_with_viewport(self.view)

        self.set_canvas(self.sw)
        self.sw.show_all()

        self._show_object_picker = gobject.timeout_add(1000, \
            self._show_picker_cb)


    def _show_picker_cb(self):
        if not self._want_document:
            return

        chooser = ObjectChooser(_('Choose document'), self,
            gtk.DIALOG_MODAL |
            gtk.DIALOG_DESTROY_WITH_PARENT)

        try:
            result = chooser.run()
            if result == gtk.RESPONSE_ACCEPT:
                jobject = chooser.get_selected_object()
                if jobject and jobject.file_path:
                    self.read_file(jobject.file_path)
        finally:
            chooser.destroy()
            del chooser

    def read_file(self, file_path):
        self._want_document = False

        tempfile = os.path.join(self.get_activity_root(), 'instance', \
            'tmp%i' % time.time())
       
        os.link(file_path, tempfile)
        gobject.idle_add(self.__set_file_idle_cb, tempfile)

    def __set_file_idle_cb(self, file_path):
        self.view.set_file_location(file_path)

        self.zoom = int(self.metadata.get('zoom', '0'))
        if self.zoom > 0:
            self.view.set_zoom(self.zoom)

        return True

    def write_file(self, file_path):
        self.metadata['zoom'] = str(self.zoom)

    def __view_toolbar_go_fullscreen_cb(self, view_toolbar):
        self._old_zoom = self.view.get_property('zoom') #XXX: Hack
        # Zoom to fit screen if possible
        screen = self.get_screen()
        zoom = self.view.calculate_optimal_zoom(screen.get_width(), screen.get_height())
        self.view.set_zoom(zoom)
        
        self.fullscreen()

    def __window_state_event_cb(self, window, event):
        if event.changed_mask & gtk.gdk.WINDOW_STATE_FULLSCREEN:
            if not self.window.get_state() & gtk.gdk.WINDOW_STATE_FULLSCREEN:
                self.view.set_zoom(self._old_zoom)
