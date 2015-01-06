# Copyright (C) 2008, One Laptop per Child
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

# The sharing bits have been taken from ReadEtexts

from __future__ import division

from sugar3.activity import activity
import logging

from gettext import gettext as _

import time
import os
import math
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject

from sugar3.graphics.alert import NotifyAlert
from sugar3.graphics.objectchooser import ObjectChooser
from sugar3 import mime
from sugar3.graphics.toolbutton import ToolButton
from sugar3.graphics.toolbarbox import ToolbarBox
from sugar3.graphics.icon import Icon
from sugar3.activity.widgets import ActivityToolbarButton
from sugar3.activity.widgets import StopButton
from sugar3.graphics import style
from sugar3.graphics.alert import Alert
from sugar3 import network
from sugar3.datastore import datastore

try:
    from gi.repository import SugarGestures
    GESTURES_AVAILABLE = True
except:
    GESTURES_AVAILABLE = False


import telepathy
import dbus

import ImageView


class ProgressAlert(Alert):
    """
    Progress alert with a progressbar - to show the advance of a task
    """

    def __init__(self, timeout=5, **kwargs):
        Alert.__init__(self, **kwargs)

        self._pb = Gtk.ProgressBar()
        self._msg_box.pack_start(self._pb, False, False, 0)
        self._pb.set_size_request(int(Gdk.Screen.width() * 9. / 10.), -1)
        self._pb.set_fraction(0.0)
        self._pb.show()

    def set_fraction(self, fraction):
        # update only by 10% fractions
        if int(fraction * 100) % 10 == 0:
            self._pb.set_fraction(fraction)
            self._pb.queue_draw()
            # force updating the progressbar
            while Gtk.events_pending():
                Gtk.main_iteration_do(True)


class ImageViewerHTTPRequestHandler(network.ChunkedGlibHTTPRequestHandler):
    """HTTP Request Handler for transferring document while collaborating.

    RequestHandler class that integrates with Glib mainloop. It writes
    the specified file to the client in chunks, returning control to the
    mainloop between chunks.

    """

    def translate_path(self, path):
        """Return the filepath to the shared document."""
        return self.server.filepath


class ImageViewerHTTPServer(network.GlibTCPServer):
    """HTTP Server for transferring document while collaborating."""

    def __init__(self, server_address, filepath):
        """Set up the GlibTCPServer with the ImageViewerHTTPRequestHandler.

        filepath -- path to shared document to be served.
        """
        self.filepath = filepath
        network.GlibTCPServer.__init__(self, server_address,
                                       ImageViewerHTTPRequestHandler)


class ImageViewerURLDownloader(network.GlibURLDownloader):
    """URLDownloader that provides content-length and content-type."""

    def get_content_length(self):
        """Return the content-length of the download."""
        if self._info is not None:
            return int(self._info.headers.get('Content-Length'))

    def get_content_type(self):
        """Return the content-type of the download."""
        if self._info is not None:
            return self._info.headers.get('Content-type')
        return None

IMAGEVIEWER_STREAM_SERVICE = 'imageviewer-activity-http'


class ImageViewerActivity(activity.Activity):

    def __init__(self, handle):
        activity.Activity.__init__(self, handle)
        self._object_id = handle.object_id

        self._zoom_out_button = None
        self._zoom_in_button = None
        self.previous_image_button = None
        self.next_image_button = None
        self._fileserver = None
        self._fileserver_tube_id = None

        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(Gtk.PolicyType.ALWAYS,
                                        Gtk.PolicyType.ALWAYS)
        # disable sharing until a file is opened
        self.max_participants = 1

        # Don't use the default kinetic scrolling, let the view do the
        # drag-by-touch and pinch-to-zoom logic.
        self.scrolled_window.set_kinetic_scrolling(False)

        self.view = ImageView.ImageViewer()

        # Connect to the touch signal for performing drag-by-touch.
        self.view.add_events(Gdk.EventMask.TOUCH_MASK)
        self._touch_hid = self.view.connect('touch-event',
                                            self.__touch_event_cb)
        self.scrolled_window.add(self.view)
        self.view.show()

        if GESTURES_AVAILABLE:
            # Connect to the zoom signals for performing
            # pinch-to-zoom.
            zoom_controller = SugarGestures.ZoomController()
            zoom_controller.attach(self,
                                   SugarGestures.EventControllerFlags.NONE)

            zoom_controller.connect('began', self.__zoomtouch_began_cb)
            zoom_controller.connect('scale-changed',
                                    self.__zoomtouch_changed_cb)
            zoom_controller.connect('ended', self.__zoomtouch_ended_cb)

        self._progress_alert = None

        toolbar_box = ToolbarBox()
        self._add_toolbar_buttons(toolbar_box)
        self.set_toolbar_box(toolbar_box)
        toolbar_box.show()

        if self._object_id is None:
            empty_widgets = Gtk.EventBox()
            empty_widgets.modify_bg(Gtk.StateType.NORMAL,
                                    style.COLOR_WHITE.get_gdk_color())

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            mvbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            vbox.pack_start(mvbox, True, False, 0)

            image_icon = Icon(pixel_size=style.LARGE_ICON_SIZE,
                              icon_name='imageviewer',
                              stroke_color=style.COLOR_BUTTON_GREY.get_svg(),
                              fill_color=style.COLOR_TRANSPARENT.get_svg())
            mvbox.pack_start(image_icon, False, False, style.DEFAULT_PADDING)

            label = Gtk.Label('<span foreground="%s"><b>%s</b></span>' %
                              (style.COLOR_BUTTON_GREY.get_html(),
                              _('No image')))
            label.set_use_markup(True)
            mvbox.pack_start(label, False, False, style.DEFAULT_PADDING)

            hbox = Gtk.Box()
            open_image_btn = Gtk.Button()
            open_image_btn.connect('clicked', self._show_picker_cb)
            add_image = Gtk.Image.new_from_stock(Gtk.STOCK_ADD,
                                                 Gtk.IconSize.BUTTON)
            buttonbox = Gtk.Box()
            buttonbox.pack_start(add_image, False, True, 0)
            buttonbox.pack_end(Gtk.Label(_('Choose an image')), True, True, 5)
            open_image_btn.add(buttonbox)
            hbox.pack_start(open_image_btn, True, False, 0)
            mvbox.pack_start(hbox, False, False, style.DEFAULT_PADDING)

            empty_widgets.add(vbox)
            empty_widgets.show_all()
            self.set_canvas(empty_widgets)
        else:
            self.set_canvas(self.scrolled_window)
            self.scrolled_window.show()

        self.unused_download_tubes = set()
        self._want_document = True
        self._download_content_length = 0
        self._download_content_type = None
        # Status of temp file used for write_file:
        self._tempfile = None
        self._close_requested = False
        self.connect("shared", self._shared_cb)
        h = hash(self._activity_id)
        self.port = 1024 + (h % 64511)

        self.is_received_document = False

        if self.shared_activity:
            # We're joining, and we don't already have the document.
            if self.get_shared():
                # Already joined for some reason, just get the document
                self._joined_cb(self)
            else:
                self._progress_alert = ProgressAlert()
                self._progress_alert.props.title = _('Please wait')
                self._progress_alert.props.msg = _('Starting connection...')
                self.add_alert(self._progress_alert)
                # Wait for a successful join before trying to get the document
                self.connect("joined", self._joined_cb)

        Gdk.Screen.get_default().connect('size-changed', self._configure_cb)

        GObject.idle_add(self._get_image_list)

    def __touch_event_cb(self, widget, event):
        coords = event.get_coords()
        if event.type == Gdk.EventType.TOUCH_BEGIN:
            self.view.start_dragtouch(coords)
        elif event.type == Gdk.EventType.TOUCH_UPDATE:
            self.view.update_dragtouch(coords)
        elif event.type == Gdk.EventType.TOUCH_END:
            self.view.finish_dragtouch(coords)

    def __zoomtouch_began_cb(self, controller):
        self.view.start_zoomtouch(controller.get_center())

        # Don't listen to touch signals until pinch-to-zoom ends.
        self.view.disconnect(self._touch_hid)

    def __zoomtouch_changed_cb(self, controller, scale):
        self.view.update_zoomtouch(controller.get_center(), scale)

    def __zoomtouch_ended_cb(self, controller):
        self.view.finish_zoomtouch()
        self._touch_hid = self.view.connect('touch-event',
                                            self.__touch_event_cb)

    def _get_image_list(self):
        value = mime.GENERIC_TYPE_IMAGE
        mime_types = mime.get_generic_type(value).mime_types
        (self.image_list, self.image_count) = datastore.find({'mime_type':
                                                               mime_types})

    def _add_toolbar_buttons(self, toolbar_box):
        self._seps = []

        self.activity_button = ActivityToolbarButton(self)
        toolbar_box.toolbar.insert(self.activity_button, 0)
        self.activity_button.show()

        self._zoom_out_button = ToolButton('zoom-out')
        self._zoom_out_button.set_tooltip(_('Zoom out'))
        self._zoom_out_button.connect('clicked', self.__zoom_out_cb)
        toolbar_box.toolbar.insert(self._zoom_out_button, -1)
        self._zoom_out_button.show()

        self._zoom_in_button = ToolButton('zoom-in')
        self._zoom_in_button.set_tooltip(_('Zoom in'))
        self._zoom_in_button.connect('clicked', self.__zoom_in_cb)
        toolbar_box.toolbar.insert(self._zoom_in_button, -1)
        self._zoom_in_button.show()

        zoom_tofit_button = ToolButton('zoom-best-fit')
        zoom_tofit_button.set_tooltip(_('Fit to window'))
        zoom_tofit_button.connect('clicked', self.__zoom_tofit_cb)
        toolbar_box.toolbar.insert(zoom_tofit_button, -1)
        zoom_tofit_button.show()

        zoom_original_button = ToolButton('zoom-original')
        zoom_original_button.set_tooltip(_('Original size'))
        zoom_original_button.connect('clicked', self.__zoom_original_cb)
        toolbar_box.toolbar.insert(zoom_original_button, -1)
        zoom_original_button.show()

        if self._object_id is None:
            self._seps.append(Gtk.SeparatorToolItem())
            toolbar_box.toolbar.insert(self._seps[-1], -1)
            self._seps[-1].show()

            self.previous_image_button = ToolButton('go-previous-paired')
            self.previous_image_button.set_tooltip(_('Previous Image'))
            self.previous_image_button.props.sensitive = False
            self.previous_image_button.connect('clicked',
                                                self.__previous_image_cb)
            toolbar_box.toolbar.insert(self.previous_image_button, -1)
            self.previous_image_button.show()

            self.next_image_button = ToolButton('go-next-paired')
            self.next_image_button.set_tooltip(_('Next Image'))
            self.next_image_button.props.sensitive = False
            self.next_image_button.connect('clicked', self.__next_image_cb)
            toolbar_box.toolbar.insert(self.next_image_button, -1)
            self.next_image_button.show()

        self._seps.append(Gtk.SeparatorToolItem())
        toolbar_box.toolbar.insert(self._seps[-1], -1)
        self._seps[-1].show()

        rotate_anticlockwise_button = ToolButton('rotate_anticlockwise')
        rotate_anticlockwise_button.set_tooltip(_('Rotate anticlockwise'))
        rotate_anticlockwise_button.connect('clicked',
                                            self.__rotate_anticlockwise_cb)
        toolbar_box.toolbar.insert(rotate_anticlockwise_button, -1)
        rotate_anticlockwise_button.show()

        rotate_clockwise_button = ToolButton('rotate_clockwise')
        rotate_clockwise_button.set_tooltip(_('Rotate clockwise'))
        rotate_clockwise_button.connect('clicked', self.__rotate_clockwise_cb)
        toolbar_box.toolbar.insert(rotate_clockwise_button, -1)
        rotate_clockwise_button.show()

        self._seps.append(Gtk.SeparatorToolItem())
        toolbar_box.toolbar.insert(self._seps[-1], -1)
        self._seps[-1].show()

        fullscreen_button = ToolButton('view-fullscreen')
        fullscreen_button.set_tooltip(_('Fullscreen'))
        fullscreen_button.connect('clicked', self.__fullscreen_cb)
        toolbar_box.toolbar.insert(fullscreen_button, -1)
        fullscreen_button.show()

        separator = Gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        toolbar_box.toolbar.insert(separator, -1)
        separator.show()

        stop_button = StopButton(self)
        toolbar_box.toolbar.insert(stop_button, -1)
        stop_button.show()

    def _configure_cb(self, event=None):
        if Gdk.Screen.width() <= style.GRID_CELL_SIZE * 12:
            for sep in self._seps:
                sep.hide()
        else:
            for sep in self._seps:
                sep.show()

    def _update_zoom_buttons(self):
        self._zoom_in_button.set_sensitive(self.view.can_zoom_in())
        self._zoom_out_button.set_sensitive(self.view.can_zoom_out())

    def __previous_image_cb(self, button):
        self.current_image_index -= 1
        self.make_button_sensitive()
        jobject = self.image_list[self.current_image_index]
        self._object_id = jobject.object_id
        self.read_file(jobject.file_path, update=True)

    def __next_image_cb(self, button):
        self.current_image_index += 1
        self.make_button_sensitive()
        jobject = self.image_list[self.current_image_index]
        self._object_id = jobject.object_id
        self.read_file(jobject.file_path, update=True)

    def __zoom_in_cb(self, button):
        self.view.zoom_in()
        self._update_zoom_buttons()

    def __zoom_out_cb(self, button):
        self.view.zoom_out()
        self._update_zoom_buttons()

    def __zoom_tofit_cb(self, button):
        self.view.zoom_to_fit()
        self._update_zoom_buttons()

    def __zoom_original_cb(self, button):
        self.view.zoom_original()
        self._update_zoom_buttons()

    def __rotate_anticlockwise_cb(self, button):
        self.view.rotate_anticlockwise()

    def __rotate_clockwise_cb(self, button):
        self.view.rotate_clockwise()

    def __fullscreen_cb(self, button):
        self.fullscreen()

    def make_button_sensitive(self):
        if self.image_count == 0 or self.image_count == 1:
            return

        if self.current_image_index == 0:
            self.next_image_button.props.sensitive = True
            self.previous_image_button.props.sensitive = False
        elif self.current_image_index == self.image_count - 1:
            self.previous_image_button.props.sensitive = True
            self.next_image_button.props.sensitive = False
        else:
            self.next_image_button.props.sensitive = True
            self.previous_image_button.props.sensitive = True

    def _show_picker_cb(self, button):
        if not self._want_document:
            return

        chooser = ObjectChooser(parent=self,
                                what_filter=mime.GENERIC_TYPE_IMAGE)

        try:
            result = chooser.run()
            if result == Gtk.ResponseType.ACCEPT:
                jobject = chooser.get_selected_object()
                if jobject and jobject.file_path:
                    self._object_id = jobject.object_id
                    self.read_file(jobject.file_path)
                    self.set_canvas(self.scrolled_window)
                    self.scrolled_window.show()
        finally:
            self.current_image_index = self.image_list.index(
                                        next(image for image in self.image_list
                                        if image.object_id == self._object_id))
            self.make_button_sensitive()
            chooser.destroy()
            del chooser

    def read_file(self, file_path, update=False):
        if self._object_id is None or self.shared_activity:
            # read_file is call because the canvas is visible
            # but we need check if is not the case of empty file
            return

        self._want_document = False
        # enable collaboration
        self.activity_button.page.share.props.sensitive = True

        tempfile = os.path.join(self.get_activity_root(), 'instance',
                                'tmp%i' % time.time())

        os.link(file_path, tempfile)
        self._tempfile = tempfile
        self.view.set_file_location(tempfile, update=update)

        zoom = self.metadata.get('zoom', None)
        if zoom is not None:
            self.view.set_zoom(float(zoom))

    def write_file(self, file_path):
        if self._tempfile:
            self.metadata['activity'] = self.get_bundle_id()
            self.metadata['zoom'] = str(self.view.get_zoom())
            if self._close_requested:
                os.link(self._tempfile, file_path)
                os.unlink(self._tempfile)
                self._tempfile = None
        else:
            raise NotImplementedError

    def can_close(self):
        self._close_requested = True
        return True

    def _download_result_cb(self, getter, tempfile, suggested_name, tube_id):
        if self._download_content_type == 'text/html':
            # got an error page instead
            self._download_error_cb(getter, 'HTTP Error', tube_id)
            return

        del self.unused_download_tubes

        self._tempfile = tempfile
        file_path = os.path.join(self.get_activity_root(), 'instance',
                                 '%i' % time.time())
        logging.debug("Saving file %s to datastore...", file_path)
        os.link(tempfile, file_path)
        self._jobject.file_path = file_path
        datastore.write(self._jobject, transfer_ownership=True)

        logging.debug("Got document %s (%s) from tube %u",
                      tempfile, suggested_name, tube_id)

        if self._progress_alert is not None:
            self.remove_alert(self._progress_alert)
            self._progress_alert = None

        GObject.idle_add(self.__set_file_idle_cb, self._jobject.object_id)

    def __set_file_idle_cb(self, object_id):
        dsobj = datastore.get(object_id)
        self._tempfile = dsobj.file_path
        """ This method is used when join a collaboration session """
        self.view.set_file_location(self._tempfile)
        try:
            zoom = int(self.metadata.get('zoom', '0'))
            if zoom > 0:
                self.view.set_zoom(zoom)
        except Exception:
            pass
        self.set_canvas(self.scrolled_window)
        self.scrolled_window.show_all()
        return False

    def _download_progress_cb(self, getter, bytes_downloaded, tube_id):
        if self._download_content_length > 0:
            logging.debug("Downloaded %u of %u bytes from tube %u...",
                          bytes_downloaded, self._download_content_length,
                          tube_id)
        else:
            logging.debug("Downloaded %u bytes from tube %u...",
                          bytes_downloaded, tube_id)
        total = self._download_content_length

        fraction = bytes_downloaded / total
        self._progress_alert.set_fraction(fraction)

    def _download_error_cb(self, getter, err, tube_id):
        logging.debug("Error getting document from tube %u: %s",
                      tube_id, err)
        self._alert('Failure', 'Error getting document from tube')
        self._want_document = True
        self._download_content_length = 0
        self._download_content_type = None
        GObject.idle_add(self._get_document)

    def _download_document(self, tube_id, path):
        # FIXME: should ideally have the CM listen on a Unix socket
        # instead of IPv4 (might be more compatible with Rainbow)
        chan = self.shared_activity.telepathy_tubes_chan
        iface = chan[telepathy.CHANNEL_TYPE_TUBES]
        addr = iface.AcceptStreamTube(
            tube_id,
            telepathy.SOCKET_ADDRESS_TYPE_IPV4,
            telepathy.SOCKET_ACCESS_CONTROL_LOCALHOST, 0,
            utf8_strings=True)
        logging.debug('Accepted stream tube: listening address is %r', addr)
        # SOCKET_ADDRESS_TYPE_IPV4 is defined to have addresses of type '(sq)'
        assert isinstance(addr, dbus.Struct)
        assert len(addr) == 2
        assert isinstance(addr[0], str)
        assert isinstance(addr[1], (int, long))
        assert addr[1] > 0 and addr[1] < 65536
        port = int(addr[1])

        getter = ImageViewerURLDownloader("http://%s:%d/document"
                                          % (addr[0], port))
        getter.connect("finished", self._download_result_cb, tube_id)
        getter.connect("progress", self._download_progress_cb, tube_id)
        getter.connect("error", self._download_error_cb, tube_id)
        logging.debug("Starting download to %s...", path)
        getter.start(path)
        self._download_content_length = getter.get_content_length()
        self._download_content_type = getter.get_content_type()

        return False

    def _get_document(self):
        if not self._want_document:
            return False

        # Assign a file path to download if one doesn't exist yet
        if not self._jobject.file_path:
            path = os.path.join(self.get_activity_root(), 'instance',
                                'tmp%i' % time.time())
        else:
            path = self._jobject.file_path

        # Pick an arbitrary tube we can try to download the document from
        try:
            tube_id = self.unused_download_tubes.pop()
        except (ValueError, KeyError), e:
            logging.debug('No tubes to get the document from right now: %s',
                          e)
            return False

        # Avoid trying to download the document multiple times at once
        self._want_document = False
        GObject.idle_add(self._download_document, tube_id, path)
        return False

    def _joined_cb(self, also_self):
        """Callback for when a shared activity is joined.

        Get the shared document from another participant.
        """
        self.watch_for_tubes()

        if self._progress_alert is not None:
            self._progress_alert.props.msg = _('Receiving image...')

    def _share_document(self):
        """Share the document."""
        # FIXME: should ideally have the fileserver listen on a Unix socket
        # instead of IPv4 (might be more compatible with Rainbow)

        logging.debug('Starting HTTP server on port %d', self.port)
        self._fileserver = ImageViewerHTTPServer(("", self.port),
                                                 self._tempfile)

        # Make a tube for it
        chan = self.shared_activity.telepathy_tubes_chan
        iface = chan[telepathy.CHANNEL_TYPE_TUBES]
        self._fileserver_tube_id = \
            iface.OfferStreamTube(
                IMAGEVIEWER_STREAM_SERVICE,
                {},
                telepathy.SOCKET_ADDRESS_TYPE_IPV4,
                ('127.0.0.1', dbus.UInt16(self.port)),
                telepathy.SOCKET_ACCESS_CONTROL_LOCALHOST, 0)

    def watch_for_tubes(self):
        """Watch for new tubes."""
        tubes_chan = self.shared_activity.telepathy_tubes_chan

        tubes_chan[telepathy.CHANNEL_TYPE_TUBES].connect_to_signal(
            'NewTube', self._new_tube_cb)
        tubes_chan[telepathy.CHANNEL_TYPE_TUBES].ListTubes(
            reply_handler=self._list_tubes_reply_cb,
            error_handler=self._list_tubes_error_cb)

    def _new_tube_cb(self, tube_id, initiator, tube_type, service, params,
                     state):
        """Callback when a new tube becomes available."""
        logging.debug('New tube: ID=%d initator=%d type=%d service=%s '
                      'params=%r state=%d', tube_id, initiator, tube_type,
                      service, params, state)
        if service == IMAGEVIEWER_STREAM_SERVICE:
            logging.debug('I could download from that tube')
            self.unused_download_tubes.add(tube_id)
            # if no download is in progress, let's fetch the document
            if self._want_document:
                GObject.idle_add(self._get_document)

    def _list_tubes_reply_cb(self, tubes):
        """Callback when new tubes are available."""
        for tube_info in tubes:
            self._new_tube_cb(*tube_info)

    def _list_tubes_error_cb(self, e):
        """Handle ListTubes error by logging."""
        logging.error('ListTubes() failed: %s', e)

    def _shared_cb(self, activityid):
        """Callback when activity shared.

        Set up to share the document.

        """
        # We initiated this activity and have now shared it, so by
        # definition we have the file.
        logging.debug('Activity became shared')
        self.next_image_button.props.sensitive = False
        self.previous_image_button.props.sensitive = False
        self.watch_for_tubes()
        self._share_document()

    def _alert(self, title, text=None):
        alert = NotifyAlert(timeout=5)
        alert.props.title = title
        alert.props.msg = text
        self.add_alert(alert)
        alert.connect('response', self._alert_cancel_cb)
        alert.show()

    def _alert_cancel_cb(self, alert, response_id):
        self.remove_alert(alert)
