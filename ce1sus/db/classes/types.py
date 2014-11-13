# -*- coding: utf-8 -*-

"""
(Description)

Created on Nov 6, 2014
"""
from sqlalchemy.schema import Column
from sqlalchemy.types import Unicode, Integer, UnicodeText

from ce1sus.db.classes.common import ValueTable
from ce1sus.db.common.session import Base


__author__ = 'Weber Jean-Paul'
__email__ = 'jean-paul.weber@govcert.etat.lu'
__copyright__ = 'Copyright 2013-2014, GOVCERT Luxembourg'
__license__ = 'GPL v3+'


class AttributeType(Base):

  name = Column('name', Unicode(255), nullable=False, index=True, unique=True)
  table_id = Column('table_id', Integer(1), index=True)
  description = Column('description', UnicodeText)

  def validate(self):
    # TODO: Add validation
    return True

  def to_dict(self, complete=False):
    if self.table_id:
      name = ValueTable.get_by_id(self.table_id)
    else:
      name = 'Any'
    allowed_table = {'identifier': self.table_id, 'name': name}
    return {'description': self.convert_value(self.description),
            'name': self.convert_value(self.name),
            'identifier': self.convert_value(self.identifier),
            'allowed_table': allowed_table
            }

  def populate(self, json):
    self.description = json.get('description', None)
    self.name = json.get('name', None)
    allowed_table = json.get('allowed_table', None)
    if allowed_table:
      identifier = allowed_table.get('identifier', None)
      if identifier:
        self.table_id = identifier


class AttributeViewType(Base):

  name = Column('name', Unicode(255), nullable=False, index=True, unique=True)
  description = Column('description', UnicodeText)

  def validate(self):
    # TODO: Add validation
    return True

  def to_dict(self, complete=False):
    return {'description': self.convert_value(self.description),
            'name': self.convert_value(self.name),
            'identifier': self.convert_value(self.identifier)
            }

  def populate(self, json):
    self.name = json.get('name', None)
    self.description = json.get('description', None)