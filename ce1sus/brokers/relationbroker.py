# -*- coding: utf-8 -*-

"""
(Description)

Created on Dec 19, 2013
"""

__author__ = 'Weber Jean-Paul'
__email__ = 'jean-paul.weber@govcert.etat.lu'
__copyright__ = 'Copyright 2013, GOVCERT Luxembourg'
__license__ = 'GPL v3+'

import cherrypy
from dagr.db.session import BASE
from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship
from dagr.db.broker import BrokerBase, IntegrityException
from ce1sus.brokers.valuebroker import ValueBroker
import sqlalchemy.orm.exc
from ce1sus.brokers.event.eventclasses import Attribute, Event
import thread
from sqlalchemy import or_
from sqlalchemy import distinct


# pylint: disable=R0903,R0902
class EventRelation(BASE):
  __tablename__ = 'EventRelations'
  identifier = Column('EventRelations_id', Integer, primary_key=True)
  event_id = Column(Integer, ForeignKey('Events.event_id'))
  event = relationship("Event", uselist=False,
                       primaryjoin='Event.identifier' +
                       '==EventRelation.event_id', lazy='joined')
  rel_event_id = Column(Integer, ForeignKey('Events.event_id'))
  rel_event = relationship("Event", uselist=False,
                           primaryjoin='Event.identifier' +
                       '==EventRelation.rel_event_id', lazy='joined')
  attribute_id = Column(Integer, ForeignKey('Attributes.attribute_id'))
  attribute = relationship("Attribute", uselist=False,
                       primaryjoin='Attribute.identifier' +
                       '==EventRelation.attribute_id', lazy='joined')
  rel_attribute_id = Column(Integer, ForeignKey('Attributes.attribute_id'))
  rel_attribute = relationship("Attribute", uselist=False,
                       primaryjoin='Attribute.identifier' +
                       '==EventRelation.attribute_id', lazy='joined')
  def validate(self):
    return True

class RelationBroker(BrokerBase):





  def __init__(self, session):
    BrokerBase.__init__(self, session)

  def generateAttributeRelations(self, attribute, commit=False):
    if attribute.definition.relation == 1:
      clazz = ValueBroker.getClassByAttributeDefinition(attribute.definition)
      relations = self.__lookForValueAndAttribID(clazz,
                                            attribute.value,
                                            attribute.definition.identifier,
                                            '==',
                                            True)
      # get own event
      event = attribute.object.event
      if event is None:
        event = self.session.query(Event).filter(Event.identifier == attribute.object.parentEvent_id)

      for relation in relations:

        # make insert foo
        if relation.event_id != event.identifier:

          # check if the relation is not already existing
          results = None
          if not results:
            # make relation in both ways
            relationEntry = EventRelation()
            relationEntry.event_id = event.identifier
            relationEntry.rel_event_id = relation.event_id
            relationEntry.attribute_id = attribute.identifier
            relationEntry.rel_attribute_id = relation.attribute_id
            try:
              self.insert(relationEntry, False)
            except IntegrityException:
              # do nothing if duplicate
              pass

      self.doCommit(commit)



  def getRelationsByEvent(self, event, uniqueEvents=True):

    try:
      relations = self.session.query(EventRelation).filter(
                        or_(EventRelation.event_id == event.identifier,
                            EventRelation.rel_event_id == event.identifier)
                        ).all()
      # convert to event -> relation
      results = list()
      seenEvents = list()
      for relation in relations:

        match = EventRelation()
        # check if event-> rel_event
        if relation.event_id == event.identifier:
          match.identifier = relation.identifier
          match.event_id = relation.event_id
          match.event = relation.event
          match.rel_event_id = relation.rel_event_id
          match.rel_event = relation.rel_event
          match.attribute_id = relation.attribute_id
          match.attribute = relation.attribute
          match.rel_attribute_id = relation.rel_attribute_id
          match.rel_attribute = relation.rel_attribute
        else:
          match.identifier = relation.identifier
          match.event_id = relation.rel_event_id
          match.event = relation.rel_event
          match.rel_event_id = relation.event_id
          match.rel_event = relation.event
          match.attribute_id = relation.rel_attribute_id
          match.attribute = relation.rel_attribute
          match.rel_attribute_id = relation.attribute_id
          match.rel_attribute = relation.attribute
        # else flip data
        if uniqueEvents:
          if not  relation.rel_event_id in seenEvents:
            results.append(match)
            seenEvents.append(match.rel_event_id)
        else:
          results.append(match)
      return results
    except sqlalchemy.orm.exc.NoResultFound:
      return list()
    except sqlalchemy.exc.SQLAlchemyError as e:
      self.getLogger().fatal(e)
      raise BrokerException(e)

    # convert

  def getBrokerClass(self):
    """
    overrides BrokerBase.getBrokerClass
    """
    return EventRelation


  def __lookForValueAndAttribID(self,
                                clazz,
                                value,
                                attributeDefinitionID,
                                operand='==',
                                byPassValidation=False):
    if byPassValidation:
      code = 0
    else:
      code = 12
    try:
      if operand == '==':
        return self.session.query(clazz).join(clazz.attribute).filter(
                  Attribute.def_attribute_id == attributeDefinitionID,
                  clazz.value == value,
                  Attribute.dbcode.op('&')(code) == code
                        ).all()
      if operand == '<':
        return self.session.query(clazz).join(clazz.attribute).filter(
                  Attribute.def_attribute_id == attributeDefinitionID,
                  clazz.value < value,
                  Attribute.dbcode.op('&')(code) == code
                        ).all()
      if operand == '>':
        return self.session.query(clazz).join(clazz.attribute).filter(
                  Attribute.def_attribute_id == attributeDefinitionID,
                  clazz.value > value,
                  Attribute.dbcode.op('&')(code) == code
                        ).all()
      if operand == '<=':
        return self.session.query(clazz).join(clazz.attribute).filter(
                  Attribute.def_attribute_id == attributeDefinitionID,
                  clazz.value <= value,
                  Attribute.dbcode.op('&')(code) == code
                        ).all()
      if operand == '>=':
        return self.session.query(clazz).join(clazz.attribute).filter(
                  Attribute.def_attribute_id == attributeDefinitionID,
                  clazz.value >= value,
                  Attribute.dbcode.op('&')(code) == code
                        ).all()
      if operand == 'like':
        return self.session.query(clazz).join(clazz.attribute).filter(
                  Attribute.def_attribute_id == attributeDefinitionID,
                  clazz.value.like('%{0}%'.format(value)),
                  Attribute.dbcode.op('&')(code) == code
                        ).all()
    except sqlalchemy.exc.SQLAlchemyError as e:
      self.getLogger().fatal(e)
      self.session.rollback()
      raise BrokerException(e)

  def __lookForValue(self, clazz, value, operand='=='):
    try:
      if operand == '==':
        return self.session.query(clazz, Attribute).filter(
                  clazz.value == value,
                  Attribute.dbcode.op('&')(12) == 12
                        ).all()
      if operand == '<':
        return self.session.query(clazz, Attribute).filter(
                  clazz.value < value,
                  Attribute.dbcode.op('&')(12) == 12
                        ).all()
      if operand == '>':
        return self.session.query(clazz, Attribute).filter(
                  clazz.value > value,
                  Attribute.dbcode.op('&')(12) == 12
                        ).all()
      if operand == '<=':
        return self.session.query(clazz, Attribute).filter(
                  clazz.value <= value,
                  Attribute.dbcode.op('&')(12) == 12
                        ).all()
      if operand == '>=':
        return self.session.query(clazz, Attribute).filter(
                  clazz.value >= value
                  , Attribute.dbcode.op('&')(12) == 12
                        ).all()
      if operand == 'like':
        return self.session.query(clazz, Attribute).filter(
                  clazz.value.like('%{0}%'.format(value)),
                  Attribute.dbcode.op('&')(12) == 12
                        ).all()
    except sqlalchemy.exc.SQLAlchemyError as e:
      self.getLogger().fatal(e)
      self.session.rollback()
      raise BrokerException(e)

  def lookforAttributeValue(self, attributeDefinition, value, operand='=='):
    """
    returns a list of matching values

    :param attributeDefinition: attribute definition to use for the lookup
    :type attributeDefinition: AttributeDefinition
    :param value: Value to look for
    :type value: String

    :returns: List of clazz
    """
    result = list()
    if attributeDefinition is None:
      # take all classes into account
      tables = AttributeDefinition.getTableDefinitions(False)
      for classname in tables.iterkeys():
        clazz = ValueBroker.getClassByClassString(classname)
        try:
          needle = clazz.convert(cleanPostValue(value))
          result = result + self.__lookForValue(clazz, needle, operand)
        except:
          # either it works or doesn't
          pass

    else:
      clazz = ValueBroker.getClassByAttributeDefinition(attributeDefinition)
      result = RelationBroker.__lookForValueAndAttribID(self.session,
                                              clazz,
                                            value,
                                            attributeDefinition.identifier,
                                            operand,
                                            False)

    return result