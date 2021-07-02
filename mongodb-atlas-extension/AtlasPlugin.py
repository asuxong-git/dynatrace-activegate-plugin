import requests
import re
import logging
import datetime
import socket
from ruxit.api.base_plugin import RemoteBasePlugin
import ruxit.api.exceptions
from requests.auth import HTTPDigestAuth

logger = logging.getLogger(__name__)

ATLAS_API = "https://cloud.mongodb.com/api/atlas/v1.0/groups/"


class CustomAtlasRemotePlugin(RemoteBasePlugin):
    timestamp = ""

    def initialize(self, **kwargs):
        logger.info('Initializing Ray Tong')
        self.args = {}

        self.json_config = kwargs["json_config"]

        config = kwargs["config"]
        self.groupid = config["groupid"]
        self.userid = config["userid"]
        self.token = config["token"]

        self.args['metrics'] = self.initialize_metrics(kwargs['json_config']['metrics'])

        if self.check_last_execution() is False:
            self.update_last_execution()
            

    def initialize_metrics(self, json_config_metrics):
        try:
            logger.info('initialize_metrics Ray Tong')
            results = {}

            for metric in json_config_metrics:
                result = {metric['timeseries']['key']: ''}

                results.update(result)

            return results
        except Exception as ex:
            logger.error("[atlasremoteplugin.initialize_metrics] EXCEPTION: " + str(ex))

            return

    def query(self, **kwargs):
        logger.info('Query Ray Tong')

        cluster_info = self.query_cluster_info()
        node_info = self.query_node_info()
        self.report_topology_and_results(cluster_info, node_info)
        self.update_last_execution()

    def query_metrics(self, node_info):
        logger.info('query_metrics Ray Tong')
        try:
            metrics = self.read(
                str(self.groupid) + "/processes/" + str(node_info) + "/measurements?granularity=PT1M&period=PT5M")

            return metrics
        except KeyError as ex:
            logger.error("[atlasremoteplugin.query_metrics] EXCEPTION: " + str(ex))
            return

    def query_node_info(self):
        logger.info('query_node_info')
        try:
            
            node_info = self.read(str(self.groupid) + "/processes")
            logger.info('Node Info:')
            logger.info(node_info)
            return node_info
        except KeyError:
            logger.info('Could\'n retrieve node info!', exc_info=1)

    def query_cluster_info(self):
        logger.info('query_cluster_info')
        try:
            cluster_info = self.read(str(self.groupid) + "/clusters")
            logger.info('Cluster Info:')
            logger.info(cluster_info)
            return cluster_info
        except KeyError:
            logger.info('Could\'n retrieve cluster state info!', exc_info=1)

    def report_topology_and_results(self, cluster_info, node_info):
        logger.info('report_topology_and_results')

        p = re.compile('^.*(?=(\-shard))', re.IGNORECASE)

        #### Retrieves the Cluster Info and creates the Group in Dynatrace
        for cluster in cluster_info["results"]:      
            group_temp = self.topology_builder.create_group(str(cluster["id"]), str(cluster["name"]))
            self.add_cluster_properties(group_temp, cluster)

            ###### This section parses the cluster nodes and creates an element for each node in Dynatrace
            for node in node_info["results"]:
                # match = p.match(node["hostname"])
                # 20210625 by Ray: fix fail matching
                match = p.match(node["userAlias"])                
                logger.info('match:' + match.group().upper())
                logger.info('cluster name:' + str(cluster["name"]).upper())
                if match.group().upper() == str(cluster["name"]).upper():
                    logger.info('calling if')
                    element_temp = group_temp.create_element(node["id"], node["hostname"])
                    self.add_node_properties(element_temp, node)

                    ##### Report Events
                    # events = self.report_events(element_temp)
                    # for event in events:
                    #     element_temp.report_custom_info_event(str(event["eventTypeName"]),{"Created At" : str(event["created"])}, {"Event Type" : str(event["eventTypeName"])})
                    #     print(str(event))

                    ##### This section queries the metrics for each node and matches against metrics in the JSON file
                    metrics = self.query_metrics(node["id"])
                    for metric in metrics["measurements"]:
                        if str(metric["name"]) in self.args['metrics'].keys():
                            logger.info('call if 2')
                            parsed_metrics = self.parse_metrics(metric["dataPoints"])
                            element_temp.absolute(key=str(metric["name"]), value=str(parsed_metrics))

    def read(self, path):
        logger.info('read '+ path)
        try:
            response = requests.get(ATLAS_API + path, auth=HTTPDigestAuth(str(self.userid), str(self.token)))
        except (requests.exceptions.MissingSchema, requests.exceptions.InvalidSchema, requests.exceptions.InvalidURL) \
                as ex:
            raise ruxit.api.exceptions.ConfigException(
                'URL: "%s" does not appear to be valid' % ATLAS_API + path) from ex
        except requests.exceptions.Timeout as ex:
            raise ruxit.api.exceptions.ConfigException('Timeout on connecting with "%s"' % ATLAS_API + path) from ex
        except (
                requests.exceptions.RequestException, requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError) as ex:
            raise ruxit.api.exceptions.ConfigException('Unable to connect to "%s"' % ATLAS_API + path) from ex

        if response.status_code == 401:
            raise ruxit.api.exceptions.AuthException(response)
        

        document = response.json()
        logger.info(document)
        return document

    def parse_metrics(self, dataPoints):
        logger.info('parse_metrics Ray Tong ')

        if len(dataPoints) == 0:
            return 0
        elif len(dataPoints) <= 1 and dataPoints[-1]["value"] is None:
            return 0
        elif dataPoints[-1]["value"] is None and dataPoints[-2] is None:
            return 0
        elif dataPoints[-1]["value"] is not None:
            return dataPoints[-1]["value"]
        else:
            return dataPoints[-2]["value"]

    def report_events(self, element_temp):
        logger.info('report_events Ray Tong ')

        results = []

        iso_date = datetime.datetime.strptime(self.timestamp, '%Y-%m-%d %H:%M:%S.%f').isoformat()

        events = self.read(str(self.groupid) + "/events?minDate=" + str(iso_date))

        for event in events["results"]:
            if str(element_temp.name) in event.values():
                results.append({"created": event["created"], "eventTypeName": event["eventTypeName"]})

        return results

    def check_last_execution(self):
        logger.info('check_last_execution Ray Tong ')
        # check if this is the first execution of the plugin
        if self.timestamp == "":
            return False

    def update_last_execution(self):
        logger.info('update_last_execution Ray Tong ')
        self.timestamp = str(datetime.datetime.utcnow())

    def add_cluster_properties(self, group_temp, cluster):
        logger.info('add_cluster_properties Ray Tong ')
        try:
            group_temp.report_property("Replication Factor", str(cluster["replicationFactor"]))
            group_temp.report_property("MongoDB Version", str(cluster["mongoDBVersion"]))
            group_temp.report_property("Cluster Type", str(cluster["clusterType"]))
            group_temp.report_property("Instance Size Name", str(cluster["providerSettings"]["instanceSizeName"]))
            group_temp.report_property("Region Name", str(cluster["providerSettings"]["regionName"]))
        except KeyError as ex:
            logger.warn("[atlasremoteplugin.add_cluster_properties] Key " + str(ex) + " not found")

        try:
            group_temp.report_property("Provider Name", str(cluster["providerSettings"]["backingProviderName"]))
        except KeyError:
            group_temp.report_property("Provider Name", str(cluster["providerSettings"]["providerName"]))

    def add_node_properties(self, element_temp, node_info):
        logger.info('add_node_properties Ray Tong ')
        

        try:
            node_ip = socket.gethostbyname(str(node_info["hostname"]))
            element_temp.add_endpoint(str(node_ip), node_info["port"], dnsNames=[str(node_info["hostname"])])
        except Exception as ex:
            logger.error("[atlasremoteplugin.add_node_properties] EXCEPTION: " + str(ex))

        element_temp.report_property("Hostname", str(node_info["hostname"]))
        element_temp.report_property("Port", str(node_info["port"]))
        element_temp.report_property("Version", str(node_info["version"]))
        element_temp.report_property("Type", str(node_info["typeName"]))
