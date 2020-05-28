import pytest
import json
from rdsparamsync import RDSParameter

parameter_group_values = {
    'wal_buffers':
    """
    {
        "ParameterName": "wal_buffers",
        "ParameterValue": "-1",
        "Description": "(8kB) Sets the number of disk-page buffers in shared memory for WAL.",
        "Source": "user",
        "ApplyType": "static",
        "DataType": "integer",
        "AllowedValues": "-1-262143",
        "IsModifiable": true,
        "ApplyMethod": "pending-reboot"
    }
    """,

    'wal_compression':
    """
    {
        "ParameterName": "wal_compression",
        "Description": "Compresses full-page writes written in WAL file.",
        "Source": "engine-default",
        "ApplyType": "static",
        "DataType": "boolean",
        "AllowedValues": "0,1",
        "IsModifiable": true,
        "ApplyMethod": "pending-reboot"
    }
    """,

    'vacuum_cost_delay':
    """
    {
        "ParameterName": "vacuum_cost_delay",
        "Description": "(ms) Vacuum cost delay in milliseconds.",
        "Source": "engine-default",
        "ApplyType": "dynamic",
        "DataType": "integer",
        "AllowedValues": "0-100",
        "IsModifiable": true,
        "ApplyMethod": "pending-reboot"
    }
    """,
}

def test_vacuum_cost_delay():
    param = RDSParameter(json.loads(parameter_group_values['vacuum_cost_delay']))

    assert param.value() == 'Engine default'
    assert param.is_modifiable() == True
    assert param.allowed_values() == ['0', '100']
    assert param.unit() == 'MS'
    assert param.normalize() == None

def test_wal_compression():
    param = RDSParameter(json.loads(parameter_group_values['wal_compression']))

    assert param.value() == 'Engine default'
    assert param.is_modifiable() == True
    assert param.allowed_values() == ['0', '1']
    assert param.type() == 'boolean'
    assert param.unit() == 'SCALAR'

def test_wal_buffers():
    param = RDSParameter(json.loads(parameter_group_values['wal_buffers']))

    assert param.value() == '-1'
    assert param.is_modifiable() == True
    assert param.allowed_values() == ['-1', '262143']
    assert param.unit() == '8KB'
    # assert param.normalize() == '-1'

def test_eq():
    p1 = RDSParameter(json.loads(parameter_group_values['wal_compression']))
    p2 = RDSParameter(json.loads(parameter_group_values['wal_compression']))

    assert p1 == p2

    p3 = RDSParameter(json.loads(parameter_group_values['wal_buffers']))

    assert p1 != p3
