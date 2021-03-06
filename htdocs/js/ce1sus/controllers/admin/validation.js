/**
 * 
 */

app.controller("adminValidationController", function($scope, Restangular,messages,
    $log, $routeSegment, $location, statuses, risks, tlps, analyses) {
  
  $scope.urlBase = '#/admin/validation/event/';
  
  $scope.statuses=statuses;
  $scope.risks=risks;
  $scope.tlps=tlps;
  $scope.anlysises=analyses;
  $scope.openedEvents = [];
  $scope.valiation = true;

  $scope.pushItem = function(event, guiOpen) {
    found = false;
    angular.forEach($scope.openedEvents, function(value, index) {
      if (value.identifier == event.identifier){
        found = true;
      }
    }, $log);
    if (!found) {
      var url = '/admin/validation/event/'+event.identifier;
      $scope.openedEvents.push({
        icon: '',
        title: event.title,
        section: 'main.layout.admin.validation.event',
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
      $location.path("/admin/validation/all");
    }
  };
  
  $scope.reloadPage = function() {
    $routeSegment.chain[4].reload();
  };
  $scope.$routeSegment = $routeSegment;
});

app.controller("adminValidationsController", function($scope, Restangular, messages,
    $log, $routeSegment, $location, ngTableParams) {

  
  $scope.getTlpColor = function(tlpText){
    return getTlpColor(tlpText);
  };
  $scope.eventTable = new ngTableParams({
      page: 1,            // show first page
      count: 10,           // count per page
      sorting: {
        created_at: 'desc'     // initial sorting
      } 
  }, {
      total: 0, // length of data
      getData: function($defer, params) {
        // Make restangular call
        Restangular.one("validate").one("unvalidated").get(params.url(), {"complete": false}).then(function(data) {
          if (data) {
            //Set total 
            params.total(data.total);
            //set data
            $defer.resolve(data.data);
          } else {
            //show error
          }
        }, function (response) {
          handleError(response, messages);
        });

      }
  }); 

});