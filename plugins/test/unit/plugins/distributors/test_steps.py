import os

import unittest

from mock import Mock, patch, call

from pulp_ostree.common import constants
from pulp_ostree.plugins.db import model
from pulp_ostree.plugins.distributors import steps


MODULE = 'pulp_ostree.plugins.distributors.steps'


class TestWebPublisher(unittest.TestCase):

    @patch(MODULE + '.mkdir')
    @patch(MODULE + '.configuration')
    @patch(MODULE + '.AtomicDirectoryPublishStep')
    @patch(MODULE + '.MainStep')
    def test_init(self, mock_main, mock_atomic, mock_configuration, mock_mkdir):
        repo = Mock(id='test', working_dir='/tmp/working')
        conduit = Mock()
        publish_dir = '/tmp/pub'
        master_pub_dir = '/tmp/master/pub'
        config = Mock()
        mock_configuration.get_web_publish_dir.return_value = publish_dir
        mock_configuration.get_master_publish_dir.return_value = master_pub_dir

        # test
        publisher = steps.WebPublisher(repo, conduit, config, working_dir='/tmp/working')

        # validation
        mock_atomic.assert_called_once_with(
            '/tmp/working',
            [('test', '/tmp/pub')],
            '/tmp/master/pub',
            step_type=constants.PUBLISH_STEP_OVER_HTTP)
        mock_main.assert_called_once_with(config=config)
        self.assertEquals(
            publisher.children,
            [mock_main.return_value, mock_atomic.return_value])
        mock_mkdir.assert_called_once_with(publisher.publish_dir)


class TestMainStep(unittest.TestCase):

    def test_init(self):
        main = steps.MainStep()
        self.assertEqual(main.step_id, constants.PUBLISH_STEP_MAIN)

    @patch(MODULE + '.MainStep._add_ref')
    @patch(MODULE + '.lib')
    def test_process_main(self, lib, add_ref):
        depth = 3
        units = [
            Mock(branch='branch:1', commit='commit:1', storage_path='path:1'),
            Mock(branch='branch:2', commit='commit:2', storage_path='path:2'),
        ]
        repository = Mock()
        lib.Repository.return_value = repository
        config = {
            constants.DISTRIBUTOR_CONFIG_KEY_DEPTH: '3'
        }
        parent = Mock(publish_dir='/tmp/dir-1234', config=config)

        # test
        main = steps.MainStep()
        main._get_units = Mock(return_value=units)
        main.parent = parent
        main.process_main()

        # validation
        lib.Repository.assert_called_once_with(parent.publish_dir)
        repository.create.assert_called_once_with()
        self.assertEqual(
            repository.pull_local.call_args_list,
            [
                call(u.storage_path, [u.commit], depth) for u in units
            ])
        self.assertEqual(
            add_ref.call_args_list,
            [
                call(parent.publish_dir, u.branch, u.commit) for u in units
            ])
        lib.Summary.assert_called_once_with(repository)
        lib.Summary.return_value.generate.assert_called_once_with()

    @patch(MODULE + '.get_unit_model_querysets')
    def test_get_units(self, find):
        units = [
            Mock(name='0', branch='branch:1', created=0),
            Mock(name='1', branch='branch:1', created=1),
            Mock(name='2', branch='branch:2', created=2),
            Mock(name='3', branch='branch:2', created=3),
            Mock(name='4', branch='branch:2', created=4),
            Mock(name='5', branch='branch:3', created=5),
        ]

        find.return_value = [reversed(units)]

        parent = Mock()
        parent.get_repo.return_value = Mock(id='id-1234')

        # test
        main = steps.MainStep()
        main.parent = parent
        unit_list = main._get_units()

        # validation
        find.assert_called_once_with(
            parent.get_repo.return_value.id, model.Branch)
        self.assertEqual(
            sorted(unit_list),
            sorted(
                [
                    units[1],
                    units[4],
                    units[5]
                ]))

    @patch('__builtin__.open')
    @patch(MODULE + '.mkdir')
    def test_add_ref(self, mkdir, _open):
        path = '/tmp/path'
        branch = 'fedora/x86/core'
        commit = 'test_commit'

        fp = Mock()
        fp.__enter__ = Mock(return_value=fp)
        fp.__exit__ = Mock()
        _open.return_value = fp

        # test
        steps.MainStep._add_ref(path, branch, commit)

        # validation
        path = os.path.join(path, 'refs', 'heads', os.path.dirname(branch))
        mkdir.assert_called_once_with(path)
        path = os.path.join(path, os.path.basename(branch))
        _open.assert_called_once_with(path, 'w+')
        fp.write.assert_called_once_with(commit)
        self.assertTrue(fp.__enter__.called)
        self.assertTrue(fp.__exit__.called)
