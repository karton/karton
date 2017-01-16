# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

class Image(object):
    '''
    A Karton image.
    '''

    def __init__(self, session, image_config):
        '''
        Initializes an Image instance.

        session - a runtime.Session.
        image_config - a configuration.ImageConfig to configure the image.
        '''
        self._session = session
        self._image_config = image_config
