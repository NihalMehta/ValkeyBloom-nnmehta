import pytest, time
import os
from valkey_bloom_test_case import ValkeyBloomTestCaseBase
from valkeytests.conftest import resource_port_tracker
from util.waiters import *

class TestBloomSaveRestore(ValkeyBloomTestCaseBase):

    def test_basic_save_and_restore(self):
        client = self.server.get_new_client()
        bf_add_result_1 = client.execute_command('BF.ADD testSave item')
        assert bf_add_result_1 == 1
        bf_exists_result_1 = client.execute_command('BF.EXISTS testSave item')
        assert bf_exists_result_1 == 1
        bf_info_result_1 = client.execute_command('BF.INFO testSave')
        assert(len(bf_info_result_1)) != 0
        curr_item_count_1 = client.info_obj().num_keys()
        # cmd debug digest
        server_digest = client.debug_digest()
        assert server_digest != None or 0000000000000000000000000000000000000000
        object_digest = client.execute_command('DEBUG DIGEST-VALUE testSave')

        # save rdb, restart sever
        client.bgsave()
        self.server.wait_for_save_done()
        self.server.restart(remove_rdb=False, remove_nodes_conf=False, connect_client=True)

        assert self.server.is_alive()
        wait_for_equal(lambda: self.server.is_rdb_done_loading(), True)
        restored_server_digest = client.debug_digest()
        restored_object_digest = client.execute_command('DEBUG DIGEST-VALUE testSave')
        assert restored_server_digest == server_digest
        assert restored_object_digest == object_digest
        self.server.verify_string_in_logfile("Loading RDB produced by Valkey")
        self.server.verify_string_in_logfile("Done loading RDB, keys loaded: 1, keys expired: 0")

        # verify restore results
        curr_item_count_2 = client.info_obj().num_keys()
        assert curr_item_count_2 == curr_item_count_1
        bf_exists_result_2 = client.execute_command('BF.EXISTS testSave item')
        assert bf_exists_result_2 == 1
        bf_info_result_2 = client.execute_command('BF.INFO testSave')
        assert bf_info_result_2 == bf_info_result_1

    def test_basic_save_many(self):
        client = self.server.get_new_client()
        count = 500
        for i in range(0, count):
            name = str(i) + "key"

            bf_add_result_1 = client.execute_command('BF.ADD ' + name + ' item')
            assert bf_add_result_1 == 1

        curr_item_count_1 = client.info_obj().num_keys()
        assert curr_item_count_1 == count
        # save rdb, restart sever
        client.bgsave()
        self.server.wait_for_save_done()

        self.server.restart(remove_rdb=False, remove_nodes_conf=False, connect_client=True)
        assert self.server.is_alive()
        wait_for_equal(lambda: self.server.is_rdb_done_loading(), True)
        self.server.verify_string_in_logfile("Loading RDB produced by Valkey")
        self.server.verify_string_in_logfile("Done loading RDB, keys loaded: 500, keys expired: 0")

        # verify restore results
        curr_item_count_1 = client.info_obj().num_keys()

        assert curr_item_count_1 == count


    def test_restore_failed_large_bloom_filter(self):
        client = self.server.get_new_client()
        # Increase the max allowed size of a bloom filter per bloom object to 180MB.
        # Create a large bloom filter.
        # When we try to restore this on a server with the default max allowed filter size of 64MB, start up should fail.
        updated_max_size = 180 * 1024 * 1024
        original_max_size = 64 * 1024 * 1024
        bf_add_result_1 = client.execute_command('CONFIG SET bf.bloom-memory-limit-per-filter ' + str(updated_max_size))
        client.execute_command('BF.RESERVE testSave 0.001 100000000')
        assert int(client.execute_command('BF.INFO testSave size')) > original_max_size
        bf_add_result_1 = client.execute_command('BF.ADD testSave item')
        assert bf_add_result_1 == 1
        bf_exists_result_1 = client.execute_command('BF.EXISTS testSave item')
        assert bf_exists_result_1 == 1
        bf_info_result_1 = client.execute_command('BF.INFO testSave')
        assert(len(bf_info_result_1)) != 0

        # Save rdb and try to load this on a sever. Validate module data type load fails and server does not startup.
        client.bgsave()
        self.server.wait_for_save_done()
        self.server.restart(remove_rdb=False, remove_nodes_conf=False, connect_client=False)
        logfile = os.path.join(self.testdir, self.server.args["logfile"])
        large_obj_restore_err = "Failed to restore bloom object: Contains a filter larger than the max allowed size limit."
        internal_rdb_err = "Internal error in RDB"
        self.wait_for_logfile(logfile, large_obj_restore_err)
        self.wait_for_logfile(logfile, internal_rdb_err)
        assert not self.server.is_alive()
