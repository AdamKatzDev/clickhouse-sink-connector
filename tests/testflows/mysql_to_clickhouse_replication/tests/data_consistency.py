import time

from testflows.core import *
from mysql_to_clickhouse_replication.requirements import *
from mysql_to_clickhouse_replication.tests.steps import *
from testflows.connect import Shell
from helpers.common import *
from itertools import combinations


@TestOutline
def unavailable(self, services, query=None):
    """Check for data consistency with concurrently service unavailable."""

    with Given("Receive UID"):
        uid = getuid()

    with And("I create unique table name"):
        table_name = f"test{uid}"

    clickhouse = self.context.cluster.node("clickhouse")
    mysql = self.context.cluster.node("mysql-master")

    init_sink_connector(auto_create_tables=True, topics=f"SERVER5432.test.{table_name}")

    with Given(f"I create MySQL table {table_name}"):
        create_mysql_table(
            name=table_name,
            statement=f"CREATE TABLE {table_name} "
                      "(id int(11) NOT NULL,"
                      "k int(11) NOT NULL DEFAULT 0,c char(120) NOT NULL DEFAULT '',"
                      f"pad char(60) NOT NULL DEFAULT '', PRIMARY KEY (id)) ENGINE = InnoDB;"
        )

    with When("I insert data in MySql table with concurrently service restart"):
        for node in services:
            self.context.cluster.node(f"{node}").stop()

        with Step(f"I insert data in MySql table"):
            mysql.query(
                f"INSERT INTO {table_name} values (1,2,'a','b'), (2,3,'a','b');"
            )

        if query == "update":
            with Then(f"I update data in MySql table"):
                mysql.query(
                    f"UPDATE {table_name} SET k=k+5 WHERE id=1;"
                )
        elif query == "delete":
            with Then(f"I delete data in MySql table"):
                mysql.query(
                    f"DELETE FROM {table_name} WHERE id=1;"
                )

    with And(f"Enable all services {services}"):
        for node in services:
            self.context.cluster.node(f"{node}").start()

    if query == "update":
        with And("I check that ClickHouse has updated data as MySQL"):
            for attempt in retries(count=10, timeout=100, delay=5):
                with attempt:
                    clickhouse.query(f"OPTIMIZE TABLE test.{table_name} FINAL DEDUPLICATE")

                    clickhouse.query(
                        f"SELECT * FROM test.{table_name} FINAL where _sign !=-1 FORMAT CSV",
                        message='1,7,"a","b"'
                    )
    elif query == "delete":
        with And("I check that ClickHouse table has same number of rows as MySQL table"):
            mysql_rows_after_delete = mysql.query(f"select count(*) from {table_name}").output.strip()[90:]
            for attempt in retries(count=10, timeout=100, delay=5):
                with attempt:
                    clickhouse.query(f"OPTIMIZE TABLE test.{table_name} FINAL DEDUPLICATE")

                    clickhouse.query(
                        f"SELECT count(*) FROM test.{table_name} FINAL where _sign !=-1 FORMAT CSV",
                        message=mysql_rows_after_delete
                    )
    else:
        for attempt in retries(count=10, timeout=100, delay=5):
            with attempt:
                clickhouse.query(f"OPTIMIZE TABLE test.{table_name} FINAL DEDUPLICATE")

                clickhouse.query(
                    f"SELECT id,k,c,pad FROM test.{table_name} FINAL where _sign !=-1 FORMAT CSV",
                    message='1,2,"a","b"\n2,3,"a","b"'
                )


@TestScenario
def kafka_unavailable(self):
    """Kafka unavailable"""
    unavailable(services=["kafka"])


@TestScenario
def debezium_unavailable(self):
    """Debezium unavailable"""
    unavailable(services=["debezium"], query="update")


@TestScenario
def clickhouse_unavailable(self):
    """ClickHouse unavailable"""
    unavailable(services=["clickhouse"])


@TestScenario
def schemaregistry_unavailable(self):
    """Schemaregistry unavailable"""
    xfail("doesn't create table")
    unavailable(services=["schemaregistry"])


@TestScenario
def sink_unavailable(self):
    """Sink connector unavailable"""
    unavailable(services=["sink"])


@TestSuite
def combinatoric_unavailable(self):
    """Check all possibilities of unavailable services"""
    nodes_list = ["sink", "debezium", "schemaregistry", "kafka", "clickhouse"]
    for i in range(2, 6):
        service_combinations = list(combinations(nodes_list, i))
        for combination in service_combinations:
            # Scenario(f"{combination}", test=unavailable, flags=TE)(services=combination)
            Scenario(f"{combination} unavailable", test=unavailable)(services=combination)


@TestOutline
def restart(self, services, loops=10):
    """Check for data consistency with concurrently service restart 100 times."""

    with Given("Receive UID"):
        uid = getuid()

    with And("I create unique table name"):
        table_name = f"test{uid}"
    #
    clickhouse = self.context.cluster.node("clickhouse")
    mysql = self.context.cluster.node("mysql-master")

    init_sink_connector(auto_create_tables=True, topics=f"SERVER5432.test.{table_name}")

    with Given(f"I create MySQL table {table_name}"):
        create_mysql_table(
            name=table_name,
            statement=f"CREATE TABLE {table_name} "
                      "(id int(11) NOT NULL,"
                      "k int(11) NOT NULL DEFAULT 0,c char(120) NOT NULL DEFAULT '',"
                      f"pad char(60) NOT NULL DEFAULT '', PRIMARY KEY (id)) ENGINE = InnoDB;"
        )

    with When("I insert data in MySql table with concurrently service restart"):
        Step(
            "I insert data in MySql table",
            test=insert,
            parallel=True,
        )(
            insert_number=10000, table_name=table_name,
        )

        for i in range(loops):
            with Step(f"LOOP STEP {i}"):
                for node in services:
                    self.context.cluster.node(f"{node}").restart()

    with And("I check that ClickHouse table has same number of rows as MySQL table"):
        mysql_rows = mysql.query(f"select count(*) from {table_name}").output.strip()[90:]
        for attempt in retries(count=10, timeout=100, delay=5):
            with attempt:
                clickhouse.query(f"OPTIMIZE TABLE test.{table_name} FINAL DEDUPLICATE")

                clickhouse.query(
                    f"SELECT count(*) FROM test.{table_name} FINAL where _sign !=-1 FORMAT CSV",
                    message=mysql_rows
                )


@TestScenario
def kafka_restart(self):
    """Kafka restart"""
    restart(services=["kafka"])


@TestOutline
def unstable_network_connection(self, services):
    """Check for data consistency with unstable network connection to some service."""

    with Given("Receive UID"):
        time.sleep(25)
        uid = getuid()

    with And("I create unique table name"):
        table_name = f"test{uid}"

    clickhouse = self.context.cluster.node("clickhouse")
    mysql = self.context.cluster.node("mysql-master")

    init_sink_connector(auto_create_tables=True, topics=f"SERVER5432.test.{table_name}")

    with Given(f"I create MySQL table {table_name}"):
        create_mysql_table(
            name=table_name,
            statement=f"CREATE TABLE {table_name} (col1 int4, col2 int4 NOT NULL, col3 int4 default 777)"
            f" ENGINE = InnoDB;",
        )

        with When("I insert data in MySql table with concurrent network fault"):
            with Shell() as bash:
                bash("docker network disconnect mysql_to_clickhouse_replication_env_default kafka", timeout=100)

            mysql.query(
                f"INSERT INTO {table_name} VALUES (1,2,3)"
            )

        with And("Enable network"):
            with Shell() as bash:
                bash("docker network connect mysql_to_clickhouse_replication_env_default kafka", timeout=100)

        with Then("I wait unique values from CLickHouse table equal to MySQL table"):
            for attempt in retries(count=10, timeout=100, delay=5):
                with attempt:
                    clickhouse.query(f"OPTIMIZE TABLE test.{table_name} FINAL DEDUPLICATE")

                    clickhouse.query(
                        f"SELECT * FROM test.{table_name} FINAL where _sign !=-1 FORMAT CSV",
                        message='1,2,3'
                    )


@TestScenario
def kafka_unstable_network_connection(self):
    """Kafka unstable network connection"""
    unstable_network_connection(services=["kafka"])


@TestFeature
@Name("data consistency")
def feature(self):
    """Сheck data consistency when network or service faults are introduced."""
    with Given("I enable debezium and sink connectors after kafka starts up"):
        init_debezium_connector()

    for scenario in loads(current_module(), Scenario):
        scenario()

    for suite in loads(current_module(), Suite):
        suite()