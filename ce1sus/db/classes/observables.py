# -*- coding: utf-8 -*-

"""
(Description)

Created on Nov 11, 2014
"""
from sqlalchemy.orm import relationship
from sqlalchemy.schema import Column, ForeignKey, Table
from sqlalchemy.types import Unicode, UnicodeText, Integer, BigInteger

from ce1sus.common.checks import is_object_viewable
from ce1sus.db.classes.basedbobject import ExtendedLogingInformations
from ce1sus.db.classes.common import Properties
from ce1sus.db.common.session import Base


__author__ = 'Weber Jean-Paul'
__email__ = 'jean-paul.weber@govcert.etat.lu'
__copyright__ = 'Copyright 2013-2014, GOVCERT Luxembourg'
__license__ = 'GPL v3+'


class ObservableKeyword(Base):
  observable_id = Column('observable_id', Unicode(40), ForeignKey('observables.observable_id', onupdate='cascade', ondelete='cascade'), nullable=False)
  keyword = Column('keyword', Unicode(255), nullable=False, index=True)


_REL_OBSERVABLE_COMPOSITION = Table('rel_observable_composition', Base.metadata,
                                    Column('roc_id', BigInteger, primary_key=True, nullable=False, index=True),
                                    Column('observablecomposition_id', Unicode(40), ForeignKey('observablecompositions.observablecomposition_id', ondelete='cascade', onupdate='cascade'), primary_key=True, index=True),
                                    Column('child_id', Unicode(40), ForeignKey('observables.observable_id', onupdate='cascade', ondelete='cascade'), nullable=False, index=True)
                                    )


class ObservableComposition(Base):
  parent_id = Column('parent_id', Unicode(40), ForeignKey('observables.observable_id', onupdate='cascade', ondelete='cascade'), nullable=False, index=True)
  parent = relationship('Observable')
  operator = Column('operator', Unicode(3), default=u'AND')
  observables = relationship('Observable', secondary='rel_observable_composition', lazy='dynamic')
  dbcode = Column('code', Integer, nullable=False, default=0)
  __bit_code = None

  @property
  def properties(self):
    """
    Property for the bit_value
    """
    if self.__bit_code is None:
      if self.dbcode is None:
        self.__bit_code = Properties('0', self)
      else:
        self.__bit_code = Properties(self.dbcode, self)
    return self.__bit_code

  def validate(self):
    return True

  def get_observables_for_permissions(self, event_permissions):
    if event_permissions:
      if event_permissions.can_validate:
        return self.observables.all()
      else:
        # count validated ones
        return self.observables.filter(Observable.dbcode.op('&')(1) == 1).all()
    else:
      # count shared and validated
      return self.observables.filter(Observable.dbcode.op('&')(3) == 3).all()

  def observables_count_for_permissions(self, event_permissions):
    if event_permissions:
      if event_permissions.can_validate:
        return self.observables.count()
      else:
        # count validated ones
        return self.observables.filter(Observable.dbcode.op('&')(1) == 1).count()
    else:
      # count shared and validated
      return self.observables.filter(Observable.dbcode.op('&')(3) == 3).count()

  def to_dict(self, complete=True, inflated=False, event_permissions=None):
    observables = list()
    for observable in self.get_observables_for_permissions(event_permissions):
      observables.append(observable.to_dict(complete, inflated, event_permissions))

    if observables:
      observables_count = len(observables)
    else:
      observables_count = self.observables_count_for_permissions(event_permissions)

    return {'identifier': self.convert_value(self.identifier),
            'operator': self.convert_value(self.operator),
            'observables': observables,
            'observables_count': observables_count,
            'properties': self.properties.to_dict()
            }


class Observable(ExtendedLogingInformations, Base):

  title = Column('title', Unicode(255), index=True)
  description = Column('description', UnicodeText)
  object = relationship('Object', back_populates='parent', uselist=False, lazy='joined', primaryjoin='Object.parent_id==Observable.identifier')
  observable_composition = relationship('ObservableComposition', uselist=False, lazy='joined')
  keywords = relationship('ObservableKeyword', backref='observable')
  event = relationship('Event', uselist=False, primaryjoin='Observable.event_id==Event.identifier')
  event_id = Column('event_id', Unicode(40), ForeignKey('events.event_id', onupdate='cascade', ondelete='cascade'), index=True)
  version = Column('version', Unicode(40), default=u'1.0.0', nullable=False)
  dbcode = Column('code', Integer, nullable=False, default=0)
  parent = relationship('Event', uselist=False, primaryjoin='Observable.parent_id==Event.identifier')
  parent_id = Column('parent_id', Unicode(40), ForeignKey('events.event_id', onupdate='cascade', ondelete='cascade'), index=True)
  __bit_code = None

  @property
  def properties(self):
    """
    Property for the bit_value
    """
    if self.__bit_code is None:
      if self.dbcode is None:
        self.__bit_code = Properties('0', self)
      else:
        self.__bit_code = Properties(self.dbcode, self)
    return self.__bit_code

  def validate(self):
    return True

  def get_object_for_permissions(self, event_permissions):
    if self.object:
      if is_object_viewable(self.object, event_permissions):
        return self.object
    return None

  def get_composed_observable_for_permissions(self, event_permissions):
    if self.observable_composition:
      if is_object_viewable(self.observable_composition, event_permissions):
        return self.observable_composition
    return None

  def to_dict(self, complete=True, inflated=False, event_permissions=None):
    obj = self.get_object_for_permissions(event_permissions)
    if obj:
      obj = obj.to_dict(complete, inflated, event_permissions)

    composed = self.get_composed_observable_for_permissions(event_permissions)
    if composed:
      composed = composed.to_dict(complete, inflated, event_permissions)

    if complete:
      result = {'identifier': self.convert_value(self.identifier),
                'title': self.convert_value(self.title),
                'description': self.convert_value(self.description),
                'object': obj,
                'version': self.convert_value(self.version),
                'observable_composition': composed,
                'creator_group': self.creator_group.to_dict(complete, inflated),
                'created_at': self.convert_value(self.created_at),
                'modified_on': self.convert_value(self.modified_on),
                'modifier_group': self.convert_value(self.modifier.group.to_dict(complete, inflated)),
                'properties': self.properties.to_dict()
                }
    else:
      result = {'identifier': self.convert_value(self.identifier),
                'title': self.convert_value(self.title),
                'object': obj,
                'observable_composition': composed,
                'creator_group': self.creator_group.to_dict(complete, inflated),
                'created_at': self.convert_value(self.created_at),
                'modified_on': self.convert_value(self.modified_on),
                'modifier_group': self.convert_value(self.modifier.group.to_dict(complete, inflated)),
                'properties': self.properties.to_dict()
                }

    return result

  def populate(self, json):
    self.title = json.get('title', None)
    self.description = json.get('description', None)
    self.properties.populate(json.get('properties', None))
    # TODO: make valid for inflated
