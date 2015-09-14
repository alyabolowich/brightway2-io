# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals
from eight import *

from bw2data import Database, databases
from ..export.excel import write_lci_matching
from ..errors import StrategyError
from ..migrations import migrations
from ..utils import activity_hash
from ..strategies import migrate_datasets, migrate_exchanges
from ..unlinked_data import UnlinkedData, unlinked_data
from datetime import datetime
from time import time
import functools
import warnings


class ImportBase(object):
    """Base class for format-specific importers.

    Defines workflow for applying strategies."""
    def __init__(self, *args, **kwargs):
        raise NotImplemented(u"This class should be subclassed")

    def __iter__(self):
        for ds in self.data:
            yield ds

    def apply_strategy(self, strategy):
        """Apply ``strategy`` transform to ``self.data``.

        Adds strategy name to ``self.applied_strategies``. If ``StrategyError`` is raised, print error message, but don't raise error.

        .. note:: Strategies should not partially modify data before raising ``StrategyError``.

        """
        if not hasattr(self, "applied_strategies"):
            self.applied_strategies = []
        try:
            func_name = strategy.__name__
        except AttributeError:  # Curried function
            func_name = strategy.func.__name__
        print(u"Applying strategy: {}".format(func_name))
        try:
            self.data = strategy(self.data)
            self.applied_strategies.append(func_name)
        except StrategyError as err:
            print(u"Couldn't apply strategy {}:\n\t{}".format(func_name, err))

    def apply_strategies(self, strategies=None):
        """Apply a list of strategies.

        Uses the default list ``self.strategies`` if ``strategies`` is ``None``."""
        start = time()
        func_list = self.strategies if strategies is None else strategies
        for func in func_list:
            self.apply_strategy(func)
        print(u"Applied {} strategies in {:.2f} seconds".format(
              len(func_list), time() - start))

    @property
    def unlinked(self):
        """Iterate through unique unlinked exchanges.

        Uniqueness is determined by ``activity_hash``."""
        seen = set()
        for ds in self.data:
            for exc in ds.get('exchanges', []):
                if not exc.get('input'):
                    ah = activity_hash(exc)
                    if ah in seen:
                        continue
                    else:
                        seen.add(ah)
                        yield exc

    def write_unlinked(self, name):
        """Write all data to an ``UnlikedData`` data store (not a ``Database``!)"""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            udb = UnlinkedData(name + " " + self.__class__.__name__)
        if udb.name not in unlinked_data:
            udb.register()
        unlinked_data[udb.name] = {
            'strategies': getattr(self, 'applied_strategies', []),
            'modified': datetime.now().isoformat(),
            'kind': 'database',
        }
        unlinked_data.flush()
        udb.write(self.data)
        print(u"Saved unlinked data: {}".format(udb.name))

    def _migrate_datasets(self, migration_name):
        assert migration_name in migrations, \
            u"Can't find migration {}".format(migration_name)
        self.apply_strategies([
            functools.partial(migrate_datasets, migration=migration_name)
        ])

    def _migrate_exchanges(self, migration_name):
        assert migration_name in migrations, \
            u"Can't find migration {}".format(migration_name)
        self.apply_strategies([
            functools.partial(migrate_exchanges, migration=migration_name)
        ])
