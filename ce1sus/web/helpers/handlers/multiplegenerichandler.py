# -*- coding: utf-8 -*-

"""
module handing the generic handler

Created: Sep 19, 2013
"""

__author__ = 'Weber Jean-Paul'
__email__ = 'jean-paul.weber@govcert.etat.lu'
__copyright__ = 'Copyright 2013, GOVCERT Luxembourg'
__license__ = 'GPL v3+'

from ce1sus.web.helpers.handlers.generichandler import GenericHandler

class MultipleGenericHandler(GenericHandler):

  def __init__(self):
    GenericHandler.__init__(self)

  def populateAttributes(self, params, obj, definition, user):
    attributes = list()
    values = params.get('value').split('\n');
    for value in values:
      params['value'] = value.replace('\r', '')
      attribute = GenericHandler.populateAttributes(self,
                                                    params,
                                                    obj,
                                                    definition,
                                                    user)
      attributes.append(attribute)
    return attributes

  def render(self, enabled, eventID, user, attribute=None):

      template = (self.
                  getTemplate('/events/event/attributes/handlers/multGeneric.html'))
      string = template.render(attribute=attribute, enabled=enabled)
      return string

