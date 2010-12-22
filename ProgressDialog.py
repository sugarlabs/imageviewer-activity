import gtk
from gettext import gettext as _


class ProgressDialog(gtk.Dialog):

    def __init__(self, parent):
        gtk.Dialog.__init__(self, _('Downloading...'), parent, \
                gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, \
                (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT))

        self._activity = parent

        self.connect('response', self._response_cb)

        self._pb = gtk.ProgressBar()
        self._pb.set_text(_('Retrieving shared image, please wait...'))
        self.vbox.add(self._pb)

    def _response_cb(self, dialog, response_id):
        if response_id == gtk.RESPONSE_REJECT:
            self._activity.close()
        else:
            pass

    def set_fraction(self, fraction):
        self._pb.set_fraction(fraction)
