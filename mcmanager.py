#!/usr/bin/env python

# -*- PYTHON_ARGCOMPLETE_OK -*-

"""MangaCat Manager"""

import aiohttp as http
import argparse as ap
import itertools as it
import imghdr
import logging
import typing as t
import os
import sys


#############
# Constants #
#############

__version__ = '0.0.2'

API = 'https://api.manga.cat/v1'
LOGIN = '/auth/login'
SERIES = '/series'
CHAPTERS = '/series_chapters'
ORIENTATIONS = (
    'rtl',
    'ltr',
    'ttb',
)
STATUSES = (
    'Releasing',
    'Completed',
    'Cancelled',
    'Hiatus',
    'Licensed',
)
COUNTRIES = (
    'Japan',
    'China',
    'Korea',
    'Thailand',
    'Vietnam',
    'Philippines',
    'Indonesia',
)
TAGS = (
    'Shounen',
    'Seinen',
    'Shoujo',
    'Josei',
    'Ecchi',
    'Gore',
    'Sexual Violence',
    'Smut',
    '4-Koma',
    'Adaptation',
    'Anthology',
    'Award Winning',
    'Doujinshi',
    'Fan Colored',
    'Full Color',
    'Official Colored',
    'Oneshot',
    'User Created',
    'Web Comic',
    'Action',
    'Adventure',
    'Comedy',
    'Crime',
    'Drama',
    'Fantasy',
    'Historical',
    'Horror',
    'Isekai',
    'Magical Girls',
    'Mecha',
    'Medical',
    'Mystery',
    'Philosophical',
    'Psychological',
    'Romance',
    'Sci-Fi',
    'Shoujo Ai',
    'Shounen Ai',
    'Slice of Life',
    'Sports',
    'Superhero',
    'Thriller',
    'Tragedy',
    'Wuxia',
    'Yaoi',
    'Yuri',
    'Aliens',
    'Animals',
    'Cooking',
    'Crossdressing',
    'Delinquents',
    'Demons',
    'Genderswap',
    'Ghosts',
    'Gyaru',
    'Harem',
    'Incest',
    'Loli',
    'Magic',
    'Martial Arts',
    'Military',
    'Monster Girls',
    'Monsters',
    'Music',
    'Ninja',
    'Office Workers',
    'Police',
    'Post-Apocalyptic',
    'Reincarnation',
    'Reverse Harem',
    'Samurai',
    'School Life',
    'Shota',
    'Supernatural',
    'Survival',
    'Time Travel',
    'Traditional Games',
    'Vampires',
    'Video Games',
    'Virtual Reality',
    'Zombies',
)
LANGUAGES = (
    'Arabic',
    'Bengali',
    'Brazilian',
    'Bulgarian',
    'Chinese',
    'Czech',
    'Danish',
    'Dutch',
    'English',
    'Filipino',
    'French',
    'German',
    'Greek',
    'Hebrew',
    'Hungarian',
    'Indonesian',
    'Italian',
    'Japanese',
    'Korean',
    'Lithuanian',
    'Malay',
    'Other',
    'Persian',
    'Polish',
    'Portuguese',
    'Romanian',
    'Russian',
    'Spanish',
    'Swedish',
    'Thai',
    'Turkish',
    'Vietnamese',
)

###########
# Logging #
###########

_logger = logging.getLogger('aiohttp.client')
logging.basicConfig(stream=sys.stderr, level=logging.WARN,
                    format='%(levelname)s: %(message)s')
logging.captureWarnings(True)


##############
# Formatters #
##############

class ArgFormatter(ap.HelpFormatter):
    def __init__(self, prog):
        super(ArgFormatter, self).__init__(
            prog, max_help_position=40, width=80
        )

    def _format_action_invocation(self, action):
        if not action.option_strings or action.nargs == 0:
            return super(ArgFormatter, self)._format_action_invocation(action)
        default_metavar = self._get_default_metavar_for_optional(action)
        args_string = self._format_args(action, default_metavar)
        return '%s %s' % (', '.join(action.option_strings), args_string)

    def _format_args(self, action, default_metavar):
        if action.nargs in ('*', '+'):
            return action.metavar
        return super(ArgFormatter, self)._format_args(action, default_metavar)

    def _get_help_string(self, action):
        help = action.help
        if '%(default)' not in action.help:
            if action.default not in (ap.SUPPRESS, None):
                if action.option_strings or action.nargs in ('*', '+'):
                    help += ' (default: %(default)s)'
        return help


#########
# Types #
#########

class ImageType(ap.FileType):
    def __init__(self, bufsize=-1, encoding=None, errors=None):
        super(ImageType, self).__init__('rb', bufsize, encoding, errors)

    def __call__(self, string):
        img = super(ImageType, self).__call__(string)
        head = img.read(32)
        for tf in imghdr.tests:
            if tf(head, img):
                img.seek(0)
                return img
        msg = f'"{string}" is not a valid image file'
        raise ap.ArgumentTypeError(msg)


class PositiveNumberType:
    def __init__(self, zero=True, ntype=float):
        self.min = ntype(zero)
        self.ntype = ntype

    def __call__(self, string):
        try:
            if self.ntype(string) < self.min:
                raise ValueError()
        except ValueError:
            msg = f'"{string}" is not a positive number'
            raise ap.ArgumentTypeError(msg)
        return self.ntype(string)


class DateTimeType:
    def __call__(self, string):
        from datetime import datetime
        if not string:
            return '0001-01-01T00:00:00Z'
        try:
            d = datetime.fromisoformat(string)
        except ValueError:
            msg = f'"{string}" is not a valid ISO date-time'
            raise ap.ArgumentTypeError(msg)
        else:
            return d.isoformat()


###########
# Actions #
###########

class ImageAction(ap.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        for val in values:
            try:
                if not imghdr.what(val):
                    values.remove(val)
                    _logger.debug(f'Ignoring file "{val}".')
            except OSError as err:
                if err.errno == 21:
                    _logger.debug(f'Ignoring directory "{val}".')
                else:
                    raise err
        setattr(namespace, self.dest, values)


class CredentialsAction(ap.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        from getpass import getpass
        if isinstance(values, list):
            if len(values) > 3:
                msg = 'cannot have more than 3 values'
                raise ap.ArgumentError(self, msg)
            creds = (
                self._get_input(values, 0, input, 'E-mail'),
                self._get_input(values, 1, input, 'Username', True),
                self._get_input(values, 2, getpass, 'Password')
            )
        else:
            creds = (values, None, None)
        setattr(namespace, self.dest, creds)

    @staticmethod
    def _get_input(values: t.List[str], n: int, func: t.Callable,
                   prompt: str, empty: bool = False) -> t.Optional[str]:
        if len(values) > n:
            return values[n]
        while True:
            result = func(f'{prompt}: ')
            if empty or result != '':
                return result
            else:
                sys.stderr.write(f'{prompt} cannot be empty!\n')


class NetrcAction(ap.Action):
    _default_path = os.getenv('NETRC', os.path.expanduser('~/.netrc'))

    def __call__(self, parser, namespace, values, option_string=None):
        from netrc import netrc
        netrc_file = values or self._default_path
        _logger.info('Using netrc file "%s".' % netrc_file)
        try:
            creds = netrc(netrc_file).hosts['manga.cat']
        except KeyError:
            msg = 'no "manga.cat" machine found in netrc file'
            raise ap.ArgumentError(self, msg)
        else:
            setattr(namespace, self.dest, creds)


###########
# Parsers #
###########

def _login_parser(parent: ap._SubParsersAction) -> ap.ArgumentParser:
    parser = parent.add_parser('login', formatter_class=ArgFormatter,
                               help='log into manga.cat')
    auth = _reorder_groups(parser, 'authentication arguments')[0]
    group = auth.add_mutually_exclusive_group(required=True)
    group.add_argument('-n', '--netrc', nargs='?', action=NetrcAction,
                       default=NetrcAction._default_path, metavar='FILE',
                       help='use a netrc file for authentication')
    group.add_argument('-c', '--credentials',
                       nargs='*', action=CredentialsAction,
                       metavar='[EMAIL] [USERNAME] [PASSWORD]',
                       help='provide your credentials for authentication')
    return parser


def _series_parser(parent: ap._SubParsersAction) -> ap.ArgumentParser:
    def subcommand_add(commands: ap._SubParsersAction) -> None:
        add = commands.add_parser('add', formatter_class=ArgFormatter,
                                  help='add a new series')
        req, opt = _reorder_groups(add)

        req.add_argument('-T', '--token', required=True,
                         help='use this token to authenticate')
        req.add_argument('-n', '--name', required=True,
                         help='the name of the series')
        req.add_argument('-d', '--description', required=True,
                         help='a description for the series')
        req.add_argument('-c', '--cover', required=True,
                         type=ImageType(), help='the cover of the series')

        opt.add_argument('-H', '--hentai', action='store_true', default=False,
                         help='set if this is a hentai series')
        opt.add_argument('-C', '--country',
                         default='Japan', choices=COUNTRIES,
                         help='the country of origin of the series')
        opt.add_argument('-s', '--status',
                         default='Releasing', choices=STATUSES,
                         help='the status of the series')
        opt.add_argument('-o', '--orientation',
                         default='rtl', choices=ORIENTATIONS,
                         help='the default orientation of the series')
        opt.add_argument('-a', '--aliases', nargs='+', metavar='ALIASES...',
                         help='other names of the series')
        opt.add_argument('-t', '--tags', nargs='+', choices=TAGS,
                         metavar='{%s}...' % ','.join(TAGS),
                         help='some tags for the series')
        opt.add_argument('-r', '--raw', metavar='RAW_URL',
                         help='the URL to the raw version of the series')
        opt.add_argument('--mu-id', metavar='MU_ID', type=int,
                         help='the ID of the series on MangaUpdates')
        opt.add_argument('--mal-id', metavar='MAL_ID', type=int,
                         help='the ID of the series on MyAnimeList')
        opt.add_argument('--bw-id', metavar='BW_ID', type=int,
                         help='the ID of the series on BookWalker')
        opt.add_argument('--amzn-id', metavar='AMAZON_ID', type=str,
                         help='the ID of the series on Amazon JP')

    parser = parent.add_parser('series', formatter_class=ArgFormatter,
                               help='manage series')
    commands = parser.add_subparsers(title='subcommands', dest='subcommand')
    commands.required = True
    subcommand_add(commands)
    return parser


def _chapters_parser(parent: ap._SubParsersAction) -> ap.ArgumentParser:
    def subcommand_add(commands: ap._SubParsersAction) -> None:
        add = commands.add_parser('add', formatter_class=ArgFormatter,
                                  help='add a new chapter')
        req, opt = _reorder_groups(add)

        req.add_argument('-T', '--token', required=True,
                         help='use this token to authenticate')
        req.add_argument('-t', '--title', required=True,
                         help='the title of the chapter')
        req.add_argument('-s', '--series', required=True, type=int,
                         help='the MangaCat ID of the chapter\'s series')
        req.add_argument('-f', '--files', required=True, nargs='+',
                         action=ImageAction, metavar='FILES...',
                         help='the image files of the chapter')
        req.add_argument('-g', '--groups', nargs='+',
                         required=True, metavar='GROUPS...',
                         help='the names of the chapter\'s groups')

        opt.add_argument('-na', '--number-absolute',
                         type=PositiveNumberType(),
                         metavar='CHAPTER_NUMBER', default=0.0,
                         help='the absolute number of the chapter')
        opt.add_argument('-nv', '--number-volume',
                         type=PositiveNumberType(),
                         metavar='NUMBER_IN_VOLUME', default=0.0,
                         help='the number of the chapter in its volume')
        opt.add_argument('-vn', '--volume-number',
                         type=PositiveNumberType(ntype=int),
                         metavar='VOLUME_NUMBER', default=0,
                         help='the volume number of the chapter')
        opt.add_argument('-H', '--hidden',
                         default=False, action='store_true',
                         help='set to hide the chapter')
        opt.add_argument('-l', '--language',
                         default='English', choices=LANGUAGES,
                         help='the language of the translation')

    parser = parent.add_parser('chapters', formatter_class=ArgFormatter,
                               help='manage chapters')
    commands = parser.add_subparsers(title='subcommands', dest='subcommand')
    commands.required = True
    subcommand_add(commands)
    return parser


def get_parser() -> ap.ArgumentParser:
    parser = ap.ArgumentParser(description=__doc__)
    parser.add_argument('-V', '--version', action='version',
                        version=f'{__doc__} v{__version__}')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help='increase the verbosity level (up to 2)')
    commands = parser.add_subparsers(title='commands', dest='command')
    commands.required = True
    _login_parser(commands)
    _series_parser(commands)
    _chapters_parser(commands)
    return parser


###########
# Helpers #
###########

def _test_extra(h: bytes, _) -> t.Optional[str]:
    if h[:12] == b'\x00\x00\x00\x0CjP  \x0D\x0A\x87\x0A':
        return 'jp2'
    if h[:4] == b'\xFF\x4F\xFF\x51':
        return 'j2k'
    if h[:4] == b'\x00\x00\x01\x00':
        return 'ico'


imghdr.tests.append(_test_extra)


def _reorder_groups(parser: ap.ArgumentParser, title: str =
                    'required arguments') -> t.List[ap._ArgumentGroup]:
    parser.add_argument_group(title=title)
    parser._action_groups.insert(1, parser._action_groups.pop())
    return parser._action_groups[1:]


async def _post_json(session: http.ClientSession,
                     url: str, data: t.Dict, token: str = None) -> str:
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    async with session.post(url, json=data, headers=headers) as res:
        try:
            body = await res.json()
        except http.ContentTypeError:
            _logger.error(await res.text())
        except http.ClientError as err:
            _logger.error(f'{err.status} - {err.message}')
        else:
            _logger.debug(body)
            return body


async def _post_files(session: http.ClientSession, url: str,
                      files: t.List[os.PathLike], token: str = None) -> int:
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    # TODO: maybe make these concurrent?
    for chunk in it.zip_longest(*[iter(files)] * 5):
        chunk = list(filter(None.__ne__, chunk))
        form = http.FormData()
        for f in chunk:
            form.add_field('data', open(f, 'rb'))

        _logger.info(f'Uploading files: {", ".join(chunk)}')
        async with session.post(url, data=form, headers=headers) as res:
            try:
                body = await res.text()
                if not body:
                    _logger.error('Empty response')
                    return 1
                _logger.debug(body)
            except http.ClientError as err:
                _logger.error(f'{err.status} - {err.message}')
    return 0


############
# Commands #
############

async def login(args: ap.Namespace, session: http.ClientSession) -> int:
    creds = args.credentials or args.netrc
    data = {
        'confirmed_password': creds[2],
        'email': creds[0],
        'password': creds[2],
        'username': creds[1]
    }

    res = await _post_json(session, API + LOGIN, data)
    if not res:
        _logger.error('Empty response')
        return 1

    print(f'Authentication token: {res["user"]["token"]}')
    return 0


async def series_add(args: ap.Namespace, session: http.ClientSession) -> int:
    # TODO: implement this
    raise NotImplementedError()


async def chapters_add(args: ap.Namespace, session: http.ClientSession) -> int:
    data = {
        'title': args.title,
        'series': {'id': args.series},
        'number_absolute': str(args.number_absolute),
        'number_volume': str(args.number_volume),
        'volume_number': str(args.volume_number),
        'groups': [{'name': g} for g in args.groups],
        'language': args.language,
        'published': not args.hidden,
    }

    res = await _post_json(session, API + CHAPTERS, data, args.token)
    if not res:
        _logger.error('Empty response.')
        return 1

    url = f'{API}{CHAPTERS}/{res["id"]}'
    ret = await _post_files(session, url, args.files, args.token)

    print(f'Added chapter with ID: {res["id"]}')
    return ret


########
# Main #
########

async def main(args: t.List[str], parser: ap.ArgumentParser) -> int:
    args = parser.parse_args(args=args)
    _logger.setLevel(_logger.level - args.verbose * 10)

    headers = {'User-Agent': f'mcmanager.py/{__version__}'}
    async with http.ClientSession(headers=headers) as session:
        if args.command == 'login':
            return await login(args, session)
        else:
            func = f'{args.command}_{args.subcommand}'
            return await globals()[func](args, session)
    return 3

if __name__ == '__main__':
    parser = get_parser()
    try:
        __import__('argcomplete').autocomplete(parser)
    except ImportError:
        pass
    finally:
        from asyncio import run
        sys.exit(run(main(sys.argv[1:], parser)))
