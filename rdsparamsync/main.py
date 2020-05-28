"""
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
import logging

logger = logging.getLogger()

from prettytable import PrettyTable  # Pretty table output
from colorama import Fore

colorama.init()


def _error(text):
    print(Fore.RED, "\b{}".format(text), Fore.RESET)
    exit(1)


def _result(text):
    print(Fore.GREEN, "\b{}".format(text), Fore.RESET)


def _json(command):
    """Parse JSON returned by a CLI command."""
    return json.loads(subprocess.check_output(command.split(" ")))


# I don't have to paginate myself, it's nice
def _parameter_group(name):
    """Get the Parameter Group from AWS API."""
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
    return None


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
    def __init__(self, data):
        assert data is not None
        self.data = data

    def name(self):
        raise NotImplementedError

    def value(self):
        raise NotImplementedError

    def unit(self):
        raise NotImplementedError

    def allowed_values(self):
        return NotImplementedError

    def normalize(self):
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
    def name(self):
        return self.data["name"]

    def value(self):
        return self.data["setting"]

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
        param = _exec(
            conn, "SELECT * FROM pg_settings WHERE name = %s", (name,)
        ).fetchone()
        if param is None:
            return UnknownPostgreSQLParameter(name)
        else:
            return cls(param)


class UnknownPostgreSQLParameter(PostgreSQLParameter):
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


@click.command()
# @click.option(
#     "--db-url",
#     required=False,
#     default=None,
#     help="The connection string for the PostgreSQL database.",
# )
@click.option(
    "--target-db", required=True, help="The target database.",
)
@click.option(
    "--parameter-group", required=False, help="Parameter group to compare to.",
)
@click.option("--other-db", required=False, help="Database to compare to.")
def main(target_db, parameter_group, other_db):
    # Give me one or the other
    # assert db_identifier is not None and parameter_group is not None

    # else:
    # parameter_group_name = parameter_group

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
        if b is None:
            b = UnknownPostgreSQLParameter({"name": a.name()})
        if a != b:
            diffs += 1
            table.add_row([a.name(), a.value(), b.value(), b.unit().lower()])

    if diffs == 0:
        _result("No differences.")
    else:
        print(table)


if __name__ == "__main__":
    main()
