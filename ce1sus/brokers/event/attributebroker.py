# -*- coding: utf-8 -*-

"""This module provides container classes and interfaces
for inserting data into the database.

Created on Jul 9, 2013
"""

__author__ = 'Weber Jean-Paul'
__email__ = 'jean-paul.weber@govcert.etat.lu'
__copyright__ = 'Copyright 2013, GOVCERT Luxembourg'
__license__ = 'GPL v3+'

from dagr.db.broker import BrokerBase, ValidationException, \
NothingFoundException, TooManyResultsFoundException, \
BrokerException
import sqlalchemy.orm.exc
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from dagr.db.session import BASE
from dagr.db.broker import DateTime
from ce1sus.brokers.permission.permissionclasses import User
from dagr.helpers.validator.objectvalidator import ObjectValidator
from ce1sus.brokers.definition.definitionclasses import AttributeDefinition
from ce1sus.brokers.definition.attributedefinitionbroker import \
                                              AttributeDefinitionBroker
from ce1sus.brokers.valuebroker import ValueBroker
from ce1sus.web.helpers.handlers.base import HandlerBase
from dagr.db.broker import IntegrityException
from ce1sus.api.restclasses import RestAttribute
from ce1sus.helpers.bitdecoder import BitValue
from dagr.helpers.string import cleanPostValue
from ce1sus.brokers.relationbroker import RelationBroker


class AttributeBroker(BrokerBase):
  """
  This broker handles all operations on attribute objects
  """
  def __init__(self, session):
    BrokerBase.__init__(self, session)
    self.valueBroker = ValueBroker(session)
    self.attributeDefinitionBroker = AttributeDefinitionBroker(session)
    self.relationBroker = RelationBroker(session)

  def getBrokerClass(self):
    """
    overrides BrokerBase.getBrokerClass
    """
    return Attribute

  def getSetValues(self, attribute):
    """sets the real values for the given attribute"""
    # execute select for the values
    try:
      value = self.valueBroker.getByAttribute(attribute)
      # value is an object i.e. StringValue and the value of the attribute is
      # the value of the value object
      # get handler
      handler = HandlerBase.getHandler(attribute.definition)
      # convert the attribute with the helper to a single line value
      attribute.value = handler.convertToAttributeValue(value)
      attribute.value_id = value.identifier
    except sqlalchemy.orm.exc.NoResultFound:
      raise NothingFoundException('No value found for attribute :{0}'.format(
                                                  attribute.definition.name))
    except sqlalchemy.orm.exc.MultipleResultsFound:
      raise TooManyResultsFoundException(
            'Too many results found for attribute :{0}'.format(
                                    attribute.definition.name))
    except sqlalchemy.exc.SQLAlchemyError as e:
      self.getLogger().fatal(e)
      self.session.rollback()
      raise BrokerException(e)

  def insert(self, instance, commit=True, validate=True):
    """
    overrides BrokerBase.insert
    """
    # validation of the value of the attribute first
    # get the definition containing the definition how to validate an attribute
    definition = instance.definition
    ObjectValidator.validateRegex(instance,
                                  'value',
                                  definition.regex,
                                  'The value does not match {0}'.format(
                                                            definition.regex),
                                  True)
    errors = not instance.validate()
    if errors:
      raise ValidationException('Attribute to be inserted is invalid')

    try:
      # insert value for value table
      BrokerBase.insert(self, instance, False, validate)
      # insert relations

      self.relationBroker.generateAttributeRelations(instance, False)

      self.valueBroker.inserByAttribute(instance, False)
      self.doCommit(True)

    except BrokerException as e:
      self.getLogger().fatal(e)
      self.session.rollback()
      raise BrokerException(e)

  def update(self, instance, commit=True, validate=True):
    """
    overrides BrokerBase.update
    """
    # validation of the value of the attribute first
    definition = instance.definition
    ObjectValidator.validateRegex(instance,
                                  'value',
                                  definition.regex,
                                  'The value does not match {0}'.format(
                                                          definition.regex),
                                  False)
    errors = not instance.validate()
    if errors:
      raise ValidationException('Attribute to be updated is invalid')
    try:
      BrokerBase.update(self, instance, False, validate)
      # updates the value of the value table
      self.doCommit(False)
      self.valueBroker.updateByAttribute(instance, False)
      self.doCommit(commit)
    except BrokerException as e:
      self.getLogger().fatal(e)
      self.session.rollback()
      raise BrokerException(e)

  def removeByID(self, identifier, commit=True):
    try:
      attribute = self.getByID(identifier)
      self.valueBroker.removeByAttribute(attribute, False)
        # first remove values
      self.doCommit(False)
        # remove attribute
      BrokerBase.removeByID(self,
                            identifier=attribute.identifier,
                            commit=False)
      self.doCommit(commit)
    except BrokerException as e:
      self.getLogger().fatal(e)
      self.session.rollback()
      raise BrokerException(e)

  def removeAttributeList(self, attributes, commit=True):
    """
      Removes all the attributes of the list

      :param attributes: List of attributes
      :type attributes: List of Attributes
    """
    try:
      for attribute in attributes:
        # remove attributes
        self.removeByID(attribute.identifier, False)
        self.doCommit(False)
      self.doCommit(commit)
    except BrokerException as e:
      self.getLogger().fatal(e)
      self.session.rollback()
      raise BrokerException(e)

  def lookforAttributeValue(self, attributeDefinition, value, operand='=='):
    self.relationBroker.lookforAttributeValue(attributeDefinition,
                                              value,
                                              operand)
