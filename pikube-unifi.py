import kopf
import logging
import kubernetes.config as kconfig
import kubernetes.client as kclient

unifi_crd = kclient.V1CustomResourceDefinition(
    api_version="apiextensions.k8s.io/v1",
    kind="CustomResourceDefinition",
    metadata=kclient.V1ObjectMeta(name="unifis.operators.silvertoken.github.io"),
    spec=kclient.V1CustomResourceDefinitionSpec(
        group="operators.silvertoken.github.io",
        versions=[kclient.V1CustomResourceDefinitionVersion(
            name="v1",
            served=True,
            storage=True,
            schema=kclient.V1CustomResourceValidation(
                open_apiv3_schema=kclient.V1JSONSchemaProps(
                    type="object",
                    properties={
                        "spec": kclient.V1JSONSchemaProps(
                            type="object",
                            properties = {
                                "ip_address": kclient.V1JSONSchemaProps(type="string"),
                                "dns": kclient.V1JSONSchemaProps(type="string"),
                                "image": kclient.V1JSONSchemaProps(type="string"),
                                "uid": kclient.V1JSONSchemaProps(type="string"),
                                "gid": kclient.V1JSONSchemaProps(type="string"),
                                "nfs_server": kclient.V1JSONSchemaProps(type="string"),
                                "nfs_path": kclient.V1JSONSchemaProps(type="string")
							}
                        ),
                        "status": kclient.V1JSONSchemaProps(
                            type="object",
                            x_kubernetes_preserve_unknown_fields=True
                        )
                    }
                )
            )
        )],
        scope="Namespaced",
        names=kclient.V1CustomResourceDefinitionNames(
            plural="unifis",
            singular="unifi",
            kind="Unifi",
            short_names=["uni"]
        )
    )
)

try:
	kconfig.load_kube_config()
except kconfig.ConfigException:
	kconfig.load_incluster_config()

api = kclient.ApiextensionsV1Api()
try:
	api.create_custom_resource_definition(unifi_crd)
except kclient.rest.ApiException as e:
	if e.status == 409:
		print("CRD already exists")
	else:
		raise e

@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    settings.peering.name = "unifi"
    settings.peering.mandatory = True
    
@kopf.on.create('operators.silvertoken.github.io', 'v1', 'unifis')
def on_unifi_create(namespace, spec, body, **kwargs):
	logging.debug(f"Unifi create handler is called: {body}")

	app = kclient.AppsV1Api()
	core = kclient.CoreV1Api()

	depList = app.list_namespaced_deployment(namespace=namespace, label_selector='app={}'.format(body.metadata.name))
	logging.debug("Found {d} deployments named '{n}'".format(d=len(depList.items), n=body.metadata.name))
	if len(depList.items) == 0:
		logging.info(f"Creating a new unifi deployment in namespace '{namespace}' with name: {body.metadata.name}")
		dep = gen_unifi_deployment(namespace, body.metadata.name, spec)
		logging.debug(f"Generated deployment: {dep}")
		try:
			response = app.create_namespaced_deployment(namespace=namespace, body=dep)
			logging.debug(f"Created deployment: {response}")
   
		except kclient.ApiException as e:
			logging.error("Exception calling create '{}'".format(e))
			raise kopf.PermanentError("Exception calling create '{}'".format(e))

	srvList = core.list_namespaced_service(namespace=namespace, label_selector='app={}'.format(body.metadata.name))
	logging.debug("Found {s} services named '{n}'".format(s=len(srvList.items), n=body.metadata.name))
	if len(srvList.items) == 0:
		logging.info(f"Creating a new unifi service in namespace '{namespace}' with name: {body.metadata.name}")
		srv = gen_unifi_service(namespace, body.metadata.name, spec)
		logging.debug(f"Generated Service: {srv}")
		try:
			response = core.create_namespaced_service(namespace=namespace, body=srv)
			logging.debug(f"Created service: {response}")
   
		except kclient.ApiException as e:
			logging.error("Exception calling create '{}'".format(e))
			raise kopf.PermanentError("Exception calling create '{}'".format(e))

	logging.info("Checking DNS records for unifi...")
 
	deploy_unifi_dns(namespace, body.metadata.name, spec)
				

def deploy_unifi_dns(namespace, name, spec):
	custom = kclient.CustomObjectsApi()

	dnsList = custom.list_namespaced_custom_object(
		group='operators.silvertoken.github.io',
		namespace=namespace,
		version='v1',
		plural='dns',
		label_selector='app={}'.format(name))

	logging.debug("Found {s} DNS records named '{n}'".format(s=len(dnsList['items']), n=name))
	
	if len(dnsList['items']) == 0:
		logging.info(f"Creating a new unifi DNS record in namespace '{namespace}' with name: {name}")
		body = {
			"apiVersion": "operators.silvertoken.github.io/v1",
			"kind": "DNS",
			"metadata": {
				"name": name,
				"namespace": namespace,
				"lables": {
					"app": name,
				}
			},
			"spec": {
				"ip_address": spec.get('ip_address'),
				"dns": spec.get('dns')
			}
		}
		kopf.adopt(body)
  
		try:
			response = custom.create_namespaced_custom_object(
				group='operators.silvertoken.github.io',
				namespace=namespace,
				version='v1',
				plural='dns',
				body=body
			)
			logging.debug(f"Created DNS Record: {response}")
			logging.info("Successfully cretaed DNS record")
		except kclient.ApiException as e:
			logging.error("Exception calling create '{}'".format(e))
			raise kopf.PermanentError("Exception calling create '{}'".format(e))
			
def gen_unifi_deployment(namespace, name, spec):
    dep = kclient.V1Deployment(
		metadata = kclient.V1ObjectMeta(namespace=namespace, name=name),
		spec = kclient.V1DeploymentSpec(
			selector = kclient.V1LabelSelector(match_labels={"app": name}),
			template = kclient.V1PodTemplateSpec(
				metadata = kclient.V1ObjectMeta(labels={"app": name}),
				spec =  kclient.V1PodSpec(
					containers = [kclient.V1Container(
						name = "unifi",
						image = spec.get('image'),
						ports = [
							kclient.V1ContainerPort(container_port=8080, name="http"),
							kclient.V1ContainerPort(container_port=8443, name="https")
						],
						env = [
							kclient.V1EnvVar(name="PUID", value=spec.get('uid')),
							kclient.V1EnvVar(name="PGID", value=spec.get('gid'))
						],
						volume_mounts = [
							kclient.V1VolumeMount(
								name = "nfs-unifi",
								mount_path = "/config"
							)
						]
					)],
					volumes = [
						kclient.V1Volume(
							name = "nfs-unifi",
							nfs = kclient.V1NFSVolumeSource(
								server = spec.get('nfs_server'),
								path = spec.get('nfs_path')
							)
						)
					]
				)
			)
		),
	)
    kopf.adopt(dep)
    return dep

def gen_unifi_service(namespace, name, spec):
    srv = kclient.V1Service(
		metadata = kclient.V1ObjectMeta(name = name, namespace = namespace),
		spec = kclient.V1ServiceSpec(
			selector = {"app": name },
			ports = [
				kclient.V1ServicePort(name="http", port=80, target_port=8080),
				kclient.V1ServicePort(name="https", port=443, target_port=8443)
			],
			type = "LoadBalancer",
			load_balancer_ip = spec.get('ip_address')
		)
	)
    kopf.adopt(srv)
    return srv