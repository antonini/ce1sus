

app.controller("eventController", function($scope, Restangular,messages,
    $log, $routeSegment,eventmenus, $location, statuses, risks, tlps, analyses) {
  $scope.statuses=statuses;
  $scope.risks=risks;
  $scope.tlps=tlps;
  $scope.anlysises=analyses;
  $scope.eventMenus = eventmenus;
  $scope.openedEvents = [];
  $scope.valiation = false;

  $scope.pushItem = function(event, guiOpen) {
    found = false;
    angular.forEach($scope.openedEvents, function(value, index) {
      if (value.identifier == event.identifier){
        found = true;
      }
    }, $log);
    if (!found) {
      var url = '/events/event/'+event.identifier;
      $scope.openedEvents.push({
        icon: '',
        title: event.title,
        section: 'main.layout.events.event',
        reload: false,
        close: true,
        href: url,
        identifier: event.identifier
      });
      if (guiOpen){
        $location.path(url);
      }
    }
  };

  $scope.removeItem = function(element_id) {
    gotoRoot = false;
    angular.forEach($scope.openedEvents, function(value, index) {
      if (value.identifier) {
        if (value.identifier == element_id) {
          $scope.openedEvents.splice(index, 1);
          gotoRoot = true;
        }
      }
    }, $log);
    if (gotoRoot){
      $location.path("/events/all");
    }
  };
  
  $scope.reloadPage = function() {
    $routeSegment.chain[3].reload();
  };
  $scope.$routeSegment = $routeSegment;
});

app.controller("viewEventController", function($scope, Restangular, messages,
    $log, $routeSegment, $location,$event) {
  $scope.event = $event;
  $scope.pushItem($scope.event);
  $scope.reloadPage = function(){
    $routeSegment.chain[4].reload();
  };
});

app.controller("eventObservableController", function($scope, Restangular, messages,
    $log, $routeSegment, $location,observables, $anchorScroll, Pagination) {
  $scope.permissions=$scope.event.userpermissions;
  $scope.getAttributes=function(){
    var attributes = [];
    function generateItems(object, observable, composed){
      if (object.attributes.length > 0) {
        angular.forEach(object.attributes, function(attribute, index) {
          var item = {};
          item.value = attribute.value;
          item.definition = attribute.definition;
          item.ioc = attribute.ioc;
          item.shared = attribute.shared;
          item.object = object.definition.name;
          item.observable = observable.title;
          if (composed) {
            item.composed = composed.title;
            item.composedoperator = composed.operator;
            item.composedlength = composed.observables.length;
          }
          attributes.push(item);
        }, $log);
      } else {
        var item = {};
        item.observable = observable.title;
        item.object = object.definition.name;
        item.value = 'No attributes were definied';
        attributes.push(item);
      }
      // continue with the related objects
      angular.forEach(object.related_objects, function(relObject) {
        generateItems(relObject.object, observable);
      }, $log);
    }
    
    function processObservavle(observable, composed){
      if (observable.observable_composition){
        angular.forEach(observable.observable_composition.observables, function(compobservable, index) {
          processObservavle(compobservable, observable.observable_composition);
        },$log);
      } else {
        if (observable.object) {
          generateItems(observable.object, observable, composed);
        } else {
          var item = {};
          item.observable = observable.title;
          item.object = 'No objects were definied';
          attributes.push(item);
        }
      }
    }
    
    angular.forEach($scope.observables, function(observable) {
      processObservavle(observable, null);
    }, $log);
    return attributes;
  };
  
  $scope.observables = observables;
  $scope.flat=false;
  $scope.showFlat=function(){
    $scope.flat=true;
    $scope.flatAttributes = $scope.getAttributes();
    $scope.pagination = Pagination.getNew(10,'flatAttributes');
    $scope.pagination.numPages = Math.ceil($scope.flatAttributes.length/$scope.pagination.perPage);
    $scope.pagination.setPages();
  };
  $scope.showStructured=function(){
    $scope.flat=false;
  };

  $scope.writeTD=function(attribute, pagination){
    var currentPosition = $scope.flatAttributes.indexOf(attribute);
    if (currentPosition> 0){
      if ($scope.flatAttributes[currentPosition-1].composedlength == attribute.composedlength){
        if (currentPosition == pagination.page * pagination.perPage){
          return true;
        }
        return false;
      }
      return true;
    } 
    return true;
  };
  
  $scope.getFlatTitle = function(attributeflat){
    if (attributeflat.composedoperator){
      if (attributeflat.composed){
        return attributeflat.composed;
      } else {
        return "Composed";
      }
    } else {
      if (attributeflat.observable){
        return attributeflat.observable;
      } else {
        return "Observable";
      }
    }
    return "Unknown";
  };

  $scope.getRowSpan = function(attribute, pagination){
    var rowspan = 0;
    if (attribute.composedlength) {
      var currentLength = attribute.composedlength;
      var currentPosition = $scope.flatAttributes.indexOf(attribute);
      var startindex = 0;
      for (var i = currentPosition; i >= 0; i--){
        if ($scope.flatAttributes[i].composedlength){
          if (currentLength != $scope.flatAttributes[i].composedlength){
            startindex = i;
            break;
          }
        }
      }
      var endPosition = (startindex + currentLength);
      var remaining = endPosition - (pagination.page * pagination.perPage);
      //TODO review I wonder why this works!? td is set incorrectly but stops where expected
      if (remaining > 0) {
        rowspan = remaining;
        if (startindex > 0){
          rowspan++;
        }
      } else {
        rowspan = pagination.perPage+remaining;
      }
      

    } else {
      rowspan = 1;
    }
      
    return rowspan;
  };
  $scope.dropdown = [
                       {
                         "text": "Structured",
                         "click": "showStructured()",
                         "html": true
                       },
                       {
                         "text": "Flat",
                         "click": "showFlat()",
                         "html": true
                       },
                     ];


});

app.controller("addEventController", function($scope, Restangular, messages,
    $log, $routeSegment, $location) {
  
  var original_event = {};
  $scope.event={};
  
  $scope.eventChanged = function ()
  {
    return !angular.equals($scope.event, original_event);
  };
  
  $scope.resetEvent = function ()
  {
    //Could also be done differently, but for this case the validation errors will also be resetted
    $routeSegment.chain[3].reload();
  };
  
  $scope.submitEvent = function(){
    Restangular.all("event").post($scope.event).then(function (data) {
      
      if (data) {
        $location.path("/events/event/"+ data.identifier);
      } else {
        $location.path("/events/all");
      }
      messages.setMessage({'type':'success','message':'Event sucessfully added'});
      
    }, function (response) {
      $scope.event = angular.copy(original_event);
      handleError(response, messages);
    });
  };
});

app.controller("editEventController", function($scope, Restangular, messages,
    $log, $routeSegment, $location) {

  var original_event = angular.copy($scope.event);

  $scope.eventChanged = function ()
  {
    return !angular.equals($scope.event, original_event);
  };
  
  $scope.resetEvent = function ()
  {
    $scope.event = angular.copy(original_event);
  };
  
  $scope.submitEvent = function(){
    $scope.event.put().then(function (data) {
      if (data) {
        $scope.event = data;
        //update username in case
        angular.forEach($scope.openedEvents, function(entry) {
          if (entry.identifier === data.identifier){
            entry.title = data.title;
          }
        }, $log);
        
      }
      
      messages.setMessage({'type':'success','message':'Event sucessfully edited'});
      
    }, function (response) {
      $scope.event = angular.copy(original_event);
      handleError(response, messages);
    });
    $scope.$hide();
  };

  $scope.closeModal = function(){
    $scope.event = angular.copy(original_event);
    $scope.$hide();
  };
});
app.controller("eventOverviewController", function($scope, Restangular, messages,
    $log, $routeSegment, $location, useradmin, groups, $modal) {
  $scope.isAdmin = useradmin;
  $scope.groups = groups;
  $scope.validateEvent = function(){
    //validates an event and publishes it as only users who can enter the validate section (lesser admin) can validate
    $scope.event.one('validate').put().then(function (data) {
      if (data) {
        messages.setMessage({'type':'success','message':'Event sucessfully validated'});
        $scope.removeItem($scope.event.identifier);
      }
    }, function (response) {
      handleError(response, messages);
    });
  };
  
  
  $scope.removeEvent = function(){
    
    if (confirm('Are you sure you want to delete this event?')) { 
      $scope.event.remove().then(function (data) {
        if (data) {
          //remove the selected user and then go to the first one in case it exists
          var index = 0;
          angular.forEach($scope.openedEvents, function(entry) {
            if (entry.identifier === $scope.event.identifier){
              $scope.openedEvents.splice(index, 1);
              $location.path("/events/all");
            }
            index++;
          }, $log);
          messages.setMessage({'type':'success','message':'Event sucessfully removed'});
        }
      }, function (response) {
        handleError(response, messages);
      });
    }
  };
  
  $scope.removeComment = function(comment){
    if (confirm('Are you sure you want to delete this comment?')) {
      //restangularize Element
      restangularComment = Restangular.restangularizeElement($scope.event, comment, 'comment');
      restangularComment.remove().then(function (data) {
        if (data) {
          //remove the selected user and then go to the first one in case it exists
          var index = $scope.event.comments.indexOf(comment);
          $scope.event.comments.splice(index, 1);
          messages.setMessage({'type':'success','message':'Comment sucessfully removed'});
        }
      }, function (response) {
        handleError(response, messages);
      });
    }
  };
  
  $scope.showCommentDetails = function(comment){
    $scope.commentDetails = comment;
    $modal({scope: $scope, template: 'pages/events/event/modals/commentdetails.html', show: true});
  };
  
  $scope.editCommentDetails = function(comment){
    $scope.commentDetails = comment;
    $modal({scope: $scope, template: 'pages/events/event/modals/editcomment.html', show: true});
  };
  
});

app.controller("changeOwnerController", function($scope, Restangular, messages,
    $log, $routeSegment, $http) {
  var original_group = angular.copy($scope.event.creator_group.identifier);
  $scope.ownergroup = $scope.event.creator_group.identifier;
  
  $scope.groupChanged = function (){
    return !angular.equals($scope.ownergroup, original_group);
  };
  
  $scope.resetGroup = function (){
    $scope.ownergroup = angular.copy(original_group);
  };
  
  $scope.submitGroup = function(){
    var group = null;
    angular.forEach($scope.groups, function(entry) {
      if (entry.identifier === $scope.ownergroup){
        group = entry;
      }
    }, $log);
    
    $http.put("/REST/0.3.0/event/"+$scope.event.identifier+'/changegroup', {'identifier': $scope.ownergroup}).success(function(data, status, headers, config) {
      if (data == 'OK') {
        $scope.event.creator_group = group;
        messages.setMessage({'type':'success','message':'Event owner sucessfully changed'});
      } else {
        messages.setMessage({'type':'danger','message':'Could not change group'});
      }
    }).error(function(data, status, headers, config) {
      var message = extractBodyFromHTML(data);
      
      if (status === 500) {
        message = "Internal Error occured, please contact your system administrator";
      }
      if (status === 0) {
        message = "Server is probaly gone offline";
      }
      error = new Ce1susException('Message');
      error.code = status;
      error.type = "danger";
      error.message = 'Error occured';
      error.description = message;
      message = {"type":"danger","message":status+" - "+getTextOutOfErrorMessage(error)};
      messages.setMessage(message);
    });

    $scope.$hide();

  };

  $scope.closeModal = function(){
    $scope.$hide();
  };
});

app.controller("addEventCommentController", function($scope, Restangular, messages,
    $log, $routeSegment) {
  var original_comment = {};
  $scope.comment = {};
  
  $scope.commentChanged = function (){
    return !angular.equals($scope.comment, original_comment);
  };
  
  $scope.resetComment = function (){
    $scope.comment = angular.copy(original_comment);
  };
  
  $scope.submitComment = function(){
    Restangular.one("event", $routeSegment.$routeParams.id).post('comment',$scope.comment).then(function (data) {
      messages.setMessage({'type':'success','message':'Comment sucessfully added'});
      $scope.event.comments.push(data);
    }, function (response) {
      $scope.comment = angular.copy(original_comment);
      handleError(response, messages);
    });
    $scope.$hide();
  };

  $scope.closeModal = function(){
    $scope.comment = angular.copy(original_comment);
    $scope.$hide();
  };
});

app.controller("editEventCommentController", function($scope, Restangular, messages,
    $log, $routeSegment) {
  var original_comment = angular.copy($scope.commentDetails);
  
  $scope.commentChanged = function (){
    return !angular.equals($scope.commentDetails, original_comment);
  };
  
  $scope.resetComment = function (){
    $scope.commentDetails = angular.copy(original_comment);
  };
  
  $scope.submitComment = function(){
    restangularComment = Restangular.restangularizeElement($scope.event, $scope.commentDetails, 'comment');
    restangularComment.put().then(function (data) {
      messages.setMessage({'type':'success','message':'Comment sucessfully editied'});

    }, function (response) {
      $scope.commentDetails = angular.copy(original_comment);
      handleError(response, messages);
    });
    $scope.$hide();
  };

  $scope.closeModal = function(){
    $scope.commentDetails = angular.copy(original_comment);
    $scope.$hide();
  };
});