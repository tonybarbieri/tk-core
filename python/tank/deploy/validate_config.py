"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

debugging script that validates the environments for a project.

"""

import os
import sys

# make sure that the core API is part of the pythonpath
python_path = os.path.abspath(os.path.join( os.path.dirname(__file__), "..", "python"))
sys.path.append(python_path)

from .. import api
from ..errors import TankError
from ..platform import validation

g_templates = set()
g_hooks = set()

def validate_bundle(log, tk, name, settings, manifest):

    log.info("")
    log.info("Validating %s..." % name)
    
    
    for s in settings.keys():
        if s not in manifest.keys():
            log.error("Parameter not needed: %s" % s)
        
        else: 
            default = manifest[s].get("default_value")
            
            value = settings[s]
            try:
                validation.validate_single_setting(name, tk, manifest, s, value)
            except TankError, e:
                log.error("  Parameter %s - Invalid value: %s" % (s,e))
            else:
                # validation is ok
                if default is None:
                    # no default value
                    log.info("  Parameter %s - OK [no default value specified in manifest]" % s)
                elif manifest[s].get("type") == "hook" and value == "default":
                    log.info("  Parameter %s - OK [using hook 'default']" % s)
                elif default == value:
                    log.info("  Parameter %s - OK [using default value]" % s)
                else:
                    log.warning("  Parameter %s - OK [using non-default value]" % s)
                    log.info("    |---> Current: %s" % value)
                    log.info("    \---> Default: %s" % default)
                    
                # remember templates
                if manifest[s].get("type") == "template":
                    g_templates.add(value)
                if manifest[s].get("type") == "hook":
                    g_hooks.add(value)

                     
    for r in manifest.keys():
        if r not in settings.keys():
            log.error("Required parameter missing: %s" % r)


def process_environment(log, tk, env):
    
    log.info("Processing environment %s" % env)

    for e in env.get_engines():  
        s = env.get_engine_settings(e)
        cfg_schema = env.get_engine_descriptor(e).get_configuration_schema()
        name = "Engine %s [environment %s]" % (e, env.name)
        validate_bundle(log, tk, name, s, cfg_schema)
        for a in env.get_apps(e):
            s = env.get_app_settings(e, a)
            cfg_schema = env.get_app_descriptor(e, a).get_configuration_schema()
            name = "App %s: %s [environment %s]" % (e, a, env.name)
            validate_bundle(log, tk, name, s, cfg_schema)
    
    
    
def validate_project(log, pipeline_config_root):
    """
    Adds an app to an environment
    """
    log.info("")
    log.info("")
    log.info("Welcome to the Tank Configuration validator!")
    log.info("")

    try:
        tk = api.tank_from_path(pipeline_config_root)
        envs = tk.pipeline_configuration.get_environments()
    except Exception, e:
        raise TankError("Could not find any environments for config %s: %s" % (pipeline_config_root, e))

    log.info("Found the following environments:")
    for x in envs:
        log.info("    %s" % x)
    log.info("")
    log.info("")

    # validate environments
    for env_name in envs:
        env = tk.pipeline_configuration.get_environment(env_name)
        process_environment(log, tk, env)

    log.info("")
    log.info("")
    log.info("")
        
    # check templates that are orphaned
    unused_templates = set(tk.templates.keys()) - g_templates 

    log.info("The following templates are not being used directly in any environments:")
    log.info("(they may be used inside complex data structures)")
    for ut in unused_templates:
        log.info(ut)

    log.info("")
    log.info("")
    log.info("")
    
    # check hooks that are unused
    hooks = os.listdir(tk.pipeline_configuration.get_hooks_location())
    # strip extension from file name
    all_hooks = set([ x[:-3] for x in hooks ])

    unused_hooks = all_hooks - g_hooks 

    log.info("The following hooks are not being used directly in any environments:")
    log.info("(they may be used inside complex data structures)")
    for uh in unused_hooks:
        log.info(uh)
    
    log.info("")
    log.info("")
    log.info("")
    
     




