"""
Compare parameters between two databases or parameter groups to catch drift.
"""
import psycopg2  # Postgres
import click  # CLI
import psycopg2.extras  # DictCursor
import colorama  # Pretty colors
import boto3  # AWS
import os
import subprocess
import json
import re

from prettytable import PrettyTable  # Pretty table output
from colorama import Fore

VERSION = '0.1-alpha1'

colorama.init()

__version__ = VERSION
__author__ = 'lev.kokotov@instacart.com'

def _error(text):
    """Print a nice error to the screen and exit."""
    print(Fore.RED, "\b{}".format(text), Fore.RESET)
    exit(1)


def _result(text):
    """Print a nice green message to the screen."""
    print(Fore.GREEN, "\b{}".format(text), Fore.RESET)


def _json(command):
    """Parse JSON returned by a CLI command."""
    return json.loads(subprocess.check_output(command.split(" ")))


# I don't have to paginate myself, it's nice
def _parameter_group(name):
    """Get the Parameter Group from AWS API. Parse it also."""
    return _json(
        "aws rds describe-db-parameters --db-parameter-group-name {}".format(name)
    )


def _parameter_group_form_db(db_identifier):
    """Get the name of the parameter group configured for a database."""
    rds = boto3.client("rds")

    response = rds.describe_db_instances(DBInstanceIdentifier=db_identifier)

    if len(response["DBInstances"]) == 0:
        _error("Database doesn't exist: {}".format(db_identifier))

    db_instance = response["DBInstances"][0]
    db_parameter_group = db_instance["DBParameterGroups"][0]["DBParameterGroupName"]

    return db_parameter_group


def _find(parameter, parameter_group):
    """A linear algorithm to find a matching parameter value in a parameter group.
    Since the number of parameters is low (150-200)...this is not a against decades of search
    algorithms research."""
    for p in parameter_group:
        p = RDSParameter(p)
        if p.name() == parameter:
            return p
    return UnknownPostgreSQLParameter({"name": parameter})


def _exec(cur, query, params=None):
    """Execute a query and return the cursor. Useful for debugging."""
    cur.execute(query, params)
    return cur


def _conn(db_url):
    """Create a connection to a database."""
    conn = psycopg2.connect(db_url)
    conn.set_session(autocommit=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    return conn, cur


class Parameter:
    """Base class representing a database configuration parameter."""

    def __init__(self, data):
        assert data is not None
        self.data = data

    ### Have to be implemented methods.
    def name(self):
        raise NotImplementedError

    def value(self):
        raise NotImplementedError

    def unit(self):
        raise NotImplementedError

    def allowed_values(self):
        return NotImplementedError

    ###

    # Still a WIP
    def normalize(self):
        """Translate a parameter into a human readable form."""
        # Handle the unset case:
        if self.value() == "-1":
            return self.value()
        elif self.value() == None:
            return None  # Default

        unit = self.unit()
        if unit == "SCALAR":
            return self.value()
        elif unit == "KB":
            return self.value()
        elif unit == "MS":
            return self.value()
        elif unit == "B":
            return self.value()
        elif unit == "8KB":
            return str(int(self.value()) * 8)
        elif unit == "MB":
            return str(int(self.value() * 1024))
        elif unit == "16MB":
            return str(int(self.value()) * 16 * 1024)
        elif unit == "GB":
            return str(int(self.value()) * 1024 * 1024)
        elif unit == "S":
            return str(int(self.value()) * 1000)  # ms
        elif unit == "MIN":
            return str(int(self.value()) * 60 * 1000)  # ms
        else:
            raise ValueError(
                "Unsupported unit {} for parameter {}".format(unit, self.name())
            )

    def __eq__(self, other):
        return (
            self.unit() == other.unit()
            and self.value() == other.value()
            and self.name() == other.name()
        )


class RDSParameter(Parameter):
    """Represents a parameter retrieved from AWS CLI.
    It parses a lot of useful info."""

    def name(self):
        return self.data["ParameterName"]

    def value(self):
        try:
            return self.data["ParameterValue"]
        except KeyError:
            return "Engine default"

    def type(self):
        return self.data["DataType"]

    def unit(self):
        """Extract the unit RDS is using for this metric."""
        result = re.search(r"^\((.*)\).*", self.data["Description"])
        try:
            return result.group(1).upper()  # Exclude ( and )
        except (IndexError, AttributeError):
            return "SCALAR"

    def is_modifiable(self):
        return self.data["IsModifiable"]

    def allowed_values(self):
        if not self.is_modifiable():
            return None
        elif "," in self.data["AllowedValues"]:
            return self.data["AllowedValues"].split(",")
        elif "-" in self.data["AllowedValues"]:
            t = self.data["AllowedValues"].split("-")
            # Handle negative values
            if self.data["AllowedValues"].startswith("-"):
                return ["-" + t[1], t[2]]
            else:
                return t
        else:
            raise AttributeError(
                "Insupported AllowedValues field: {}".format(self.data["AllowedValues"])
            )

    def normalize(self):
        # We cannot deduce template arguments easily...
        # TODO: figure this out
        if any(x in str(self.value()) for x in ["{", "}"]):
            return None
        else:
            super().normalize()


class PostgreSQLParameter(Parameter):
    """Represents a parameter retrieved directly
    from the PostgreSQL database."""

    def name(self):
        return self.data["name"]

    def value(self):
        return self.data["setting"][:50]

    def unit(self):
        try:
            return self.data["unit"].upper()
        except AttributeError:
            return "SCALAR"

    def is_modifiable(self):
        return False  # Can't modify anything in PG/RDS

    def allowed_values(self):
        return [str(self.data["min_value"]), str(self.data["max_value"])]

    def normalize(self):
        # Handle boolean
        if self.value() == "off":
            return "0"
        elif self.value() == "on":
            return "1"
        else:
            return super().normalize()

    @classmethod
    def from_db(cls, name, conn):
        """Get and parse the parameter from the database."""
        param = _exec(
            conn, "SELECT * FROM pg_settings WHERE name = %s", (name,)
        ).fetchone()
        if param is None:
            print("Unknown parameter: {}".format(name))
            return UnknownPostgreSQLParameter(name)
        else:
            return cls(param)

    @classmethod
    def all_settings(cls, conn):
        """Get and parse all parameters from the database."""
        params = _exec(conn, "SELECT * FROM pg_settings").fetchall()
        return list(map(lambda x: cls(x), params))


class UnknownPostgreSQLParameter(PostgreSQLParameter):
    """Represents an unknown PostgreSQL parameter. Effectively
    the "is None" case."""

    def __init__(self, name):
        super().__init__({"name": name})

    def unit(self):
        return "UNSET"

    def normalize(self):
        return None

    def value(self):
        return None

    def allowed_values(self):
        return []


# CLI
@click.group()
def main():
    pass


# TODO: Figure out how to get creds automatically based on database identifier.
@main.command()
@click.option(
    "--target-db-url", required=True, help="DSN for the target database.",
)
@click.option(
    "--other-db-url", required=True, help="DSN for the database to compare to."
)
def db(target_db_url, other_db_url):
    """Compare target DB to other DB using PostgreSQL settings."""
    ca, ra = _conn(target_db_url)
    cb, rb = _conn(other_db_url)

    params_a = PostgreSQLParameter.all_settings(ra)
    params_b = PostgreSQLParameter.all_settings(rb)

    table = PrettyTable(
        [
            "Name",
            ca.get_dsn_parameters()["host"],
            cb.get_dsn_parameters()["host"],
            "Unit",
        ]
    )

    diff = 0
    for a in params_a:
        for b in params_b:
            if a.name() == b.name():
                if a != b:
                    diff += 1
                    table.add_row([a.name(), a.value(), b.value(), a.unit()])

    if diff == 0:
        _result("No differences.")
    else:
        print(table)


@main.command()
@click.option(
    "--target-db", required=True, help="The target database.",
)
@click.option(
    "--parameter-group", required=False, help="Parameter group to compare to.",
)
@click.option("--other-db", required=False, help="Database to compare to.")
def pg(target_db, parameter_group, other_db):
    """Compare target DB to other DB using Parameter Groups."""
    parameter_group_a = _parameter_group(_parameter_group_form_db(target_db))[
        "Parameters"
    ]

    if parameter_group is None and other_db is not None:
        parameter_group_b = _parameter_group(_parameter_group_form_db(other_db))[
            "Parameters"
        ]
    elif parameter_group is not None:
        parameter_group_b = _parameter_group(parameter_group)["Parameters"]
    else:
        _error("--parameter-group or --other-db is required.")

    table = PrettyTable(["Name", target_db, (parameter_group or other_db), "Unit"])

    diffs = 0
    for a in parameter_group_a:
        a = RDSParameter(a)
        b = _find(a.name(), parameter_group_b)

        if a != b:
            diffs += 1
            table.add_row([a.name(), a.value(), b.value(), b.unit().lower()])

    if diffs == 0:
        _result("No differences.")
    else:
        print(table)
