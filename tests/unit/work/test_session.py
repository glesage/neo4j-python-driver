#!/usr/bin/env python
# -*- encoding: utf-8 -*-

# Copyright (c) "Neo4j"
# Neo4j Sweden AB [http://neo4j.com]
#
# This file is part of Neo4j.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest

from neo4j import (
    Session,
    SessionConfig,
    Transaction,
    unit_of_work,
)

from ._fake_connection import FakeConnection


@pytest.fixture()
def pool(mocker):
    pool = mocker.MagicMock()
    pool.acquire = mocker.MagicMock(side_effect=iter(FakeConnection, 0))
    return pool


def test_session_context_calls_close(mocker):
    s = Session(None, SessionConfig())
    mock_close = mocker.patch.object(s, 'close', autospec=True)
    with s:
        pass
    mock_close.assert_called_once_with()


@pytest.mark.parametrize("test_run_args", (
    ("RETURN $x", {"x": 1}), ("RETURN 1",)
))
@pytest.mark.parametrize(("repetitions", "consume"), (
    (1, False), (2, False), (2, True)
))
def test_opens_connection_on_run(pool, test_run_args, repetitions, consume):
    with Session(pool, SessionConfig()) as session:
        assert session._connection is None
        result = session.run(*test_run_args)
        assert session._connection is not None
        if consume:
            result.consume()


@pytest.mark.parametrize("test_run_args", (
    ("RETURN $x", {"x": 1}), ("RETURN 1",)
))
@pytest.mark.parametrize("repetitions", range(1, 3))
def test_closes_connection_after_consume(pool, test_run_args, repetitions):
    with Session(pool, SessionConfig()) as session:
        result = session.run(*test_run_args)
        result.consume()
        assert session._connection is None
    assert session._connection is None


@pytest.mark.parametrize("test_run_args", (
    ("RETURN $x", {"x": 1}), ("RETURN 1",)
))
def test_keeps_connection_until_last_result_consumed(pool, test_run_args):
    with Session(pool, SessionConfig()) as session:
        result1 = session.run(*test_run_args)
        result2 = session.run(*test_run_args)
        assert session._connection is not None
        result1.consume()
        assert session._connection is not None
        result2.consume()
        assert session._connection is None


def test_opens_connection_on_tx_begin(pool):
    with Session(pool, SessionConfig()) as session:
        assert session._connection is None
        with session.begin_transaction() as _:
            assert session._connection is not None


@pytest.mark.parametrize("test_run_args", (
    ("RETURN $x", {"x": 1}), ("RETURN 1",)
))
@pytest.mark.parametrize("repetitions", range(1, 3))
def test_keeps_connection_on_tx_run(pool, test_run_args, repetitions):
    with Session(pool, SessionConfig()) as session:
        with session.begin_transaction() as tx:
            for _ in range(repetitions):
                tx.run(*test_run_args)
                assert session._connection is not None


@pytest.mark.parametrize("test_run_args", (
        ("RETURN $x", {"x": 1}), ("RETURN 1",)
))
@pytest.mark.parametrize("repetitions", range(1, 3))
def test_keeps_connection_on_tx_consume(pool, test_run_args, repetitions):
    with Session(pool, SessionConfig()) as session:
        with session.begin_transaction() as tx:
            for _ in range(repetitions):
                result = tx.run(*test_run_args)
                result.consume()
                assert session._connection is not None


@pytest.mark.parametrize("test_run_args", (
        ("RETURN $x", {"x": 1}), ("RETURN 1",)
))
def test_closes_connection_after_tx_close(pool, test_run_args):
    with Session(pool, SessionConfig()) as session:
        with session.begin_transaction() as tx:
            for _ in range(2):
                result = tx.run(*test_run_args)
                result.consume()
            tx.close()
            assert session._connection is None
        assert session._connection is None


@pytest.mark.parametrize("test_run_args", (
        ("RETURN $x", {"x": 1}), ("RETURN 1",)
))
def test_closes_connection_after_tx_commit(pool, test_run_args):
    with Session(pool, SessionConfig()) as session:
        with session.begin_transaction() as tx:
            for _ in range(2):
                result = tx.run(*test_run_args)
                result.consume()
            tx.commit()
            assert session._connection is None
        assert session._connection is None


@pytest.mark.parametrize("bookmarks", (None, [], ["abc"], ["foo", "bar"]))
def test_session_returns_bookmark_directly(pool, bookmarks):
    with Session(pool, SessionConfig(bookmarks=bookmarks)) as session:
        if bookmarks:
            assert session.last_bookmark() == bookmarks[-1]
        else:
            assert session.last_bookmark() is None


@pytest.mark.parametrize(("query", "error_type"), (
    (None, ValueError),
    (1234, TypeError),
    ({"how about": "no?"}, TypeError),
    (["I don't", "think so"], TypeError),
))
def test_session_run_wrong_types(pool, query, error_type):
    with Session(pool, SessionConfig()) as session:
        with pytest.raises(error_type):
            session.run(query)


@pytest.mark.parametrize("tx_type", ("write_transaction", "read_transaction"))
def test_tx_function_argument_type(pool, tx_type):
    def work(tx):
        assert isinstance(tx, Transaction)

    with Session(pool, SessionConfig()) as session:
        getattr(session, tx_type)(work)


@pytest.mark.parametrize("tx_type", ("write_transaction", "read_transaction"))
@pytest.mark.parametrize("decorator_kwargs", (
    {},
    {"timeout": 5},
    {"metadata": {"foo": "bar"}},
    {"timeout": 5, "metadata": {"foo": "bar"}},

))
def test_decorated_tx_function_argument_type(pool, tx_type, decorator_kwargs):
    @unit_of_work(**decorator_kwargs)
    def work(tx):
        assert isinstance(tx, Transaction)

    with Session(pool, SessionConfig()) as session:
        getattr(session, tx_type)(work)


def test_session_tx_type(pool):
    with Session(pool, SessionConfig()) as session:
        tx = session.begin_transaction()
        assert isinstance(tx, Transaction)
