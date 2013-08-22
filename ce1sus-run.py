"""main file for launching ce1sus"""

import cherrypy
import os
from framework.db.session import SessionManager
from framework.helpers.debug import Log
from framework.web.helpers.templates import MakoHandler
from ce1sus.web.controllers.index import IndexController
from ce1sus.web.controllers.admin.index import AdminController
from ce1sus.web.controllers.events.events import EventsController
from ce1sus.web.controllers.admin.user import UserController
from ce1sus.web.controllers.admin.groups import GroupController
from ce1sus.web.controllers.admin.objects import ObjectController
from ce1sus.web.helpers.protection import Protector
from framework.web.helpers.webexceptions import ErrorHandler
from framework.helpers.ldaphandling import LDAPHandler
from framework.helpers.rt import RTHelper
from framework.web.helpers.config import WebConfig
from framework.web.helpers.cherrypyhandling import CherryPyHandler
from ce1sus.web.controllers.admin.attributes import AttributeController
from ce1sus.web.controllers.event.event import EventController
from ce1sus.web.controllers.event.objects import ObjectsController
from ce1sus.web.controllers.event.tickets import TicketsController
from ce1sus.web.controllers.event.groups import GroupsController
from ce1sus.web.controllers.events.search import SearchController
from ce1sus.web.controllers.event.attributes import AttributesController
from ce1sus.web.controllers.event.comments import CommentsController

def application(environ, start_response):
  bootstrap()
  #return CherryPyHandler.application(environ, start_response)
  return cherrypy.tree(environ, start_response)



def bootstrap():
  # want parent of parent directory aka ../../
  basePath = os.path.dirname(os.path.abspath(__file__))

  # setup cherrypy
  #
  #CherryPyHandler(basePath + '/config/cherrypy.conf')

  ce1susConfigFile = basePath + '/config/ce1sus.conf'

  cherrypy.config.update(basePath + '/config/cherrypy.conf')
  

  # Load 'Modules'
  
  # ErrorHandler(ce1susConfigFile)
  Log(ce1susConfigFile)
  Log.getLogger("run").debug("Loading Session")
  SessionManager(ce1susConfigFile)
  Log.getLogger("run").debug("Loading Mako")
  MakoHandler(ce1susConfigFile)
  Log.getLogger("run").debug("Loading Protector")
  Protector(ce1susConfigFile)
  Log.getLogger("run").debug("Loading RT")
  RTHelper(ce1susConfigFile)
  Log.getLogger("run").debug("Loading WebCfg")
  WebConfig(ce1susConfigFile)
  Log.getLogger("run").debug("Loading Ldap")
  LDAPHandler(ce1susConfigFile)


  # add controllers
  Log.getLogger("run").debug("Adding controllers")
  Log.getLogger("run").debug("Adding index")
  cherrypy.tree.mount(IndexController(), '/')
  CherryPyHandler.addController(IndexController(), '/')
  #Log.getLogger("run").debug("Adding admin")
  cherrypy.tree.mount(AdminController(), '/admin')
  #Log.getLogger("run").debug("Adding admin/users")
  cherrypy.tree.mount(UserController(), '/admin/users')
  #Log.getLogger("run").debug("Adding admin groups")
  cherrypy.tree.mount(GroupController(), '/admin/groups')
  #Log.getLogger("run").debug("Adding admin objects")
  cherrypy.tree.mount(ObjectController(), '/admin/objects')
  #Log.getLogger("run").debug("Adding admin attributes")
  cherrypy.tree.mount(AttributeController(), '/admin/attributes')
  #Log.getLogger("run").debug("Adding events")
  cherrypy.tree.mount(EventsController(), '/events')
  #Log.getLogger("run").debug("Adding events event")
  cherrypy.tree.mount(EventController(), '/events/event')
  #Log.getLogger("run").debug("Adding events search")
  cherrypy.tree.mount(SearchController(), '/events/search')
  #Log.getLogger("run").debug("Adding events event object")
  cherrypy.tree.mount(ObjectsController(), '/events/event/objects')
  #Log.getLogger("run").debug("Adding events event ticket")
  cherrypy.tree.mount(TicketsController(), '/events/event/tickets')
  #Log.getLogger("run").debug("Adding events event groups")
  cherrypy.tree.mount(GroupsController(), '/events/event/groups')
  #Log.getLogger("run").debug("Adding events event attribute")
  cherrypy.tree.mount(AttributesController(), '/events/event/attribute')
  #Log.getLogger("run").debug("Adding events event comment")
  cherrypy.tree.mount(CommentsController(), '/events/event/comment')




if __name__ == '__main__':

  bootstrap()
  CherryPyHandler.localRun()

