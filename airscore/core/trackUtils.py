"""
Module for operations on tracks
Use:    import trackUtils
        pil_id = compUtils.get_track_pilot(filename)

Antonio Golfari - 2018
"""

from os import path, listdir, fsdecode

from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError

from Defines import TRACKDIR, MAPOBJDIR, track_sources, track_formats
from flightresult import FlightResult
from myconn import Database
import re
from pathlib import Path
import unicodedata


def remove_accents(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return u"".join([c for c in nfkd_form if not unicodedata.combining(c)])


def extract_tracks(file, dir):
    """gets tracks from a zipfile"""
    from zipfile import ZipFile, is_zipfile

    error = 0
    """Check if file exists"""
    if is_zipfile(file):
        print(f'extracting {file} in dir: {dir}')
        """Create a ZipFile Object and load file in it"""
        try:
            with ZipFile(file, 'r') as zipObj:
                """Extract all the contents of zip file in temporary directory"""
                zipObj.extractall(dir)
        except IOError:
            print(f"Error: extracting {file} to {dir} \n")
    else:
        print(f"reading error: {file} does not exist or is not a zip file \n")
        error = 1

    return error


def get_tracks(directory):
    """Checks files and imports what appear to be tracks"""
    from Defines import track_formats
    files = []

    print(f"Directory: {directory} \n")
    print(f"Looking for files \n")

    """check files in temporary directory, and get only tracks"""
    for file in listdir(directory):
        print(f"checking: {file} \n")
        if not Path(file).name.startswith(tuple(['_', '.'])) and Path(file).suffix.strip('.') in track_formats:
            """file is a valid track"""
            files.append(path.join(directory, file))
    return files


def assign_and_import_tracks(files, task, xcontest=False, user=None, check_g_record=False, print=print):
    """Find pilots to associate with tracks"""
    from compUtils import get_registration
    from track import Track, validate_G_record, igc_parsing_config_from_yaml
    from functools import partial
    from frontendUtils import print_to_sse
    import json

    pilot_list = []

    task_id = task.id
    comp_id = task.comp_id
    task_date = task.date
    track_counter = 0
    """checking if comp requires a regisration.
    Then we create a list of registered pilots to check against tracks filename.
    This should be much faster than checking against all pilots in database through a query"""
    registration = get_registration(comp_id)
    if registration:
        """We add tracks for the registered pilots not yet scored"""
        print("Comp with registration: files will be checked against registered pilots not yet scored")
        pilot_list = get_unscored_pilots(task_id, xcontest)
        print(f"We have {len(pilot_list)} pilots to find tracks for")
    else:
        print(f"We have {len(files)} tracks to associate")
    track_path = task.file_path
    FlightParsingConfig = igc_parsing_config_from_yaml(task.igc_config_file)

    # print("found {} tracks \n".format(len(files)))
    for file in files:
        mytrack = None
        filename = path.basename(file)
        if registration:
            if len(pilot_list) == 0:
                break
            if len(pilot_list) > 0:
                # print(f"checking {filename} against {len(pilot_list)} pilots...")
                """check filenames to find pilots"""
                pilot, full_name = get_pilot_from_list(filename, pilot_list)
                if pilot:
                    """found a pilot for the track file.
                    dropping pilot from list and creating track obj"""
                    # print(f"Found a pilot to associate with file. dropping {pilot.name} from non scored list")
                    pilot_list[:] = [d for d in pilot_list if d.par_id != pilot.par_id]
                    mytrack = Track.read_file(filename=file, config=FlightParsingConfig, print=print)
        else:
            """We add track if we find a pilot in database
            that has not yet been scored"""
            mytrack = Track.read_file(filename=file, config=FlightParsingConfig, print=print)
            if get_pil_track(mytrack.par_id, task_id):
                """pilot has already been scored"""
                print(f"Pilot with ID {mytrack.par_id} has already a valid track for task with ID {task_id}")
                mytrack = None
        """check result"""
        if not mytrack:
            print(f"Track {filename} is not a valid track file, pilot not found in competition or pilot already has "
                  f"a track")
        elif not mytrack.date == task_date:
            print(f"track {filename} has a different date from task")
        else:
            """pilot is registered and has no valid track yet
            moving file to correct folder and adding to the list of valid tracks"""
            track_counter += 1
            print(f"Track {track_counter}|counter")
            mytrack.task_id = task_id
            filename_and_path = mytrack.copy_track_file(task_path=track_path, pname=full_name)
            # print(f"pilot {mytrack.par_id} associated with track {mytrack.filename}")
            pilot.track = mytrack
            print(f"processing {pilot.info.ID} {pilot.info.name}:")
            if user:
                new_print = partial(print_to_sse, id=mytrack.par_id, channel=user)
                print('***************START*******************')
            else:
                new_print = print
            if check_g_record:
                print('Checking G-Record...')
                validation = validate_G_record(filename_and_path)
                if validation == 'FAILED':
                    print('G-Record not valid')
                    data = {'par_id': pilot.par_id, 'track_id': pilot.track_id, 'Result': ''}
                    print(json.dumps(data) + '|g_record_fail')
                    continue
                if validation == 'ERROR':
                    print('Error trying to validate G-Record')
                    continue
                if validation == 'PASSED':
                    print('G-Record is valid')
            verify_and_import_track(pilot, task, print=new_print)
    print("*******************processed all tracks**********************")


def import_track(pilot, task_id):
    pilot.track.to_db(task_id)
    return pilot.track.track_id


def verify_and_import_track(pilot, task, print=print):
    from airspace import AirspaceCheck

    if task.airspace_check:
        airspace = AirspaceCheck.from_task(task)
    else:
        airspace = None
    pilot.result = FlightResult.check_flight(pilot.track.flight, task, airspace_obj=airspace,
                                             print=print)  # check flight against task
    pilot.to_db()
    if pilot.notifications:
        print(str(pilot.notifications))
    print('***************END****************')

    return pilot.result


def find_pilot(name):
    """Get pilot from name or fai
    info comes from FSDB file, as FsParticipant attributes, or from igc filename
    Not sure about best strategy to retrieve pilots ID from name and FAI n.
    """
    from db_tables import PilotView as P

    '''Gets name from string. check it is not integer'''
    if type(name) is int:
        '''name is a id number'''
        fai = name
        names = None
    else:
        fai = None
        names = name.replace("'", "''").replace('.', ' ').replace('_', ' ').replace('-', ' ').split()
        '''check if we have fai n. in names'''
        if names[0].isdigit():
            fai = names.pop(0)

    print("Trying with name... \n")
    with Database() as db:
        t = db.session.query(P.pil_id)
        if names:
            q = t.filter(P.last_name.in_(names))
            p = q.filter(P.first_name.in_(names))
        else:
            p = t.filter(P.fai_id == fai)
        pil = p.all()
        if len(pil) == 1:
            return pil.pop().pil_id
        '''try one more time if we have both names and fai'''
        if fai and names:
            if not pil:
                p = q  # if we have zero results, try with only lastname and fai
            pil = p.filter(P.fai_id == fai).all()
            if len(pil) == 1:
                return pil.pop().pil_id
    return None


def get_pil_track(par_id: int, task_id: int):
    """Get pilot result in a given task"""
    from db_tables import TblTaskResult as R

    with Database() as db:
        track_id = db.session.query(R.track_id).filter(
            and_(R.par_id == par_id, R.task_id == task_id)).scalar()
    if track_id == 0:
        """No result found"""
        print(f"Pilot with ID {par_id} has not been scored yet on task ID {task_id} \n")
    return track_id


def read_tracklog_map_result_file(track_id: int, task_id: int):
    """create task and track objects"""
    import jsonpickle
    from pathlib import Path

    res_path = f"{MAPOBJDIR}tracks/{task_id}/"
    filename = 'result_' + str(track_id) + '.track'
    fullname = Path(res_path, filename)
    # if the file does not exist
    if not Path(fullname).is_file():
        create_tracklog_map_result_file(track_id, task_id)

    with open(fullname, 'r') as f:
        return jsonpickle.decode(f.read())


def create_tracklog_map_result_file(track_id: int, task_id: int):
    import flightresult
    from task import Task
    from track import Track

    task = Task.read(task_id)
    track = Track.read_db(track_id)
    # lib = task.formula.get_lib()
    result = flightresult.FlightResult.check_flight(track.flight, task)
    result.save_tracklog_map_result_file(result.to_geojson_result(track, task), str(track_id), task_id)


def get_task_fullpath(task_id: int):
    from db_tables import TblTask as T, TblCompetition as C

    with Database() as db:
        try:
            q = db.session.query(T.task_path,
                                 C.comp_path).join(C, C.comp_id == T.comp_id).filter(T.task_id == task_id).one()
        except SQLAlchemyError:
            print(f'Get Task Path Query Error')
            return None
    return path.join(TRACKDIR, q.comp_path, q.task_path)


def get_unscored_pilots(task_id: int, xcontest=False):
    """ Gets list of registered pilots that still do not have a result
        Input:  task_id INT task database ID
        Output: list of Pilot obj."""
    from pilot import Pilot
    from participant import Participant
    from db_tables import UnscoredPilotView as U
    pilot_list = []
    with Database() as db:
        try:
            results = db.session.query(U.par_id, U.comp_id, U.ID, U.name, U.nat, U.sex, U.civl_id,
                                       U.live_id, U.glider, U.glider_cert, U.sponsor, U.xcontest_id,
                                       U.team, U.nat_team).filter(U.task_id == task_id).all()
            # if xcontest:
            #     q = q.filter(U.xcontest_id != None)
            # results = q.all()
            for p in results:
                participant = Participant()
                db.populate_obj(participant, p)
                pilot = Pilot.create(task_id=task_id, info=participant)
                pilot_list.append(pilot)
        except SQLAlchemyError as e:
            error = str(e.__dict__)
            print(f"Error trying to retrieve unscored pilots from database {error}")
            db.session.rollback()
            db.session.close()
            return error
    return pilot_list


def get_pilot_from_list(filename, pilots: list):
    """ check filename against a list of Pilot Obj.
        Looks for different information in filename

        filename:   STR file name
        pilots:     LIST Participants Obj.
    """
    from Defines import filename_formats
    '''prepare filename formats'''
    # name = r'[a-zA-Z]+'
    # id = r'[\d]+'
    # fai = r'[\da-zA-Z]+'
    # civl = r'[0-9]+'
    # live = r'[\d]+'
    # other = r'[\da-zA-Z]+'
    filename_check = dict(name=r"[a-zA-Z']+", id=r'[\d]+', fai=r'[\da-zA-Z]+', civl=r'[\d]+', live=r'[\da-zA-Z]+',
                          other=r"[a-zA-Z0-9']+")
    format_list = [re.findall(r'[\da-zA-Z]+', el) for el in filename_formats]

    '''Get string'''
    string = Path(filename).stem
    elements = re.findall(r"[\d]+|[a-zA-Z']+", string)
    num_of_el = len(elements)
    pilot = None
    if any(el for el in format_list if len(el) == num_of_el):
        '''we have a match in number of elements between filename and accepted formats'''
        for f in [el for el in format_list if len(el) == num_of_el]:
            if all(re.match(filename_check[val], elements[idx]) for idx, val in enumerate(f)):
                '''we have a match between filename and accepted formats'''
                print(f'{f}')
                print(f'{elements}')
                if any(k for k in f if k in ['id', 'live', 'civl', 'fai']):
                    '''unique id, each should find the exact pilot'''
                    for idx, val in enumerate(f):
                        print(f'{val}, {elements[idx]}')
                        if val in ['other', 'name']:
                            continue
                        elif val == 'id':
                            v = int(elements[idx])
                            a = 'ID'
                        elif val == 'civl':
                            v = int(elements[idx])
                            a = 'civl_id'
                        elif val == 'live':
                            v = elements[idx]
                            a = 'live_id'
                        elif val == 'fai':
                            v = elements[idx]
                            a = 'fai_id'
                        pilot = next((p for p in pilots if getattr(p.info, a) == v), None)
                        if pilot:
                            print(f'{a}, found {pilot.info.name}')
                            filename = remove_accents('_'.join(pilot.info.name.replace('_', ' ')
                                                               .replace("'", ' ').lower().split()))
                            return pilot, filename
                else:
                    '''no unique id in filename, using name'''
                    names = [str(elements[idx]).lower() for idx, val in enumerate(f) if val == 'name']
                    pilot = next((p for p in pilots if all(n in p.info.name.lower().split() for n in names)), None)
                    if pilot:
                        print(f'using name, found {pilot.info.name}')
                        '''we found a pilot'''
                        filename = remove_accents('_'.join(pilot.info.name.replace('_', ' ')
                                                           .replace("'", ' ').lower().split()))
                        return pilot, filename
    return None, None


# def assign_tracks(task, file_dir, pilots_list, source):
#     """ This function will look for tracks in giver dir or in task_path, and tries to associate tracks to participants.
#         For the moment we give for granted pilots need to register, as for this stage only event with registration
#         are possible.
#
#         AirScore will permit to retrieve tracks from different sources and repositories. We need to be able
#         to recognise pilot from filename.
#     """
#     from pathlib import Path
#     from igc_lib import Flight
#     import shutil
#
#     # if not file_dir:
#     #     file_dir = task.file_path
#     if len(listdir(file_dir)) == 0:
#         ''' directory is empty'''
#         print(f'directory {file_dir} is empty')
#         return None
#
#     for file in listdir(file_dir):
#         filename = fsdecode(file)  # filename is without path
#         file_ext = Path(filename).suffix[1:].lower()
#         if filename.startswith((".", "_")) or file_ext not in track_formats:
#             """file is not a valid track"""
#             print(f"Not a valid filename: {filename}")
#             pass
#
#         # TODO manage track file source (comp attr?)
#         if source:
#             pilot, idx = source.get_pilot_from_list(filename, pilots_list)
#         else:
#             pilot, idx = get_pilot_from_list(filename, pilots_list)
#
#         if pilot:
#             try:
#                 '''move track to task folder'''
#                 file_path = task.file_path
#                 full_path = path.join(file_path, filename)
#                 shutil.move(filename, full_path)
#                 '''add flight'''
#                 pilot.track.flight = Flight.create_from_file(full_path)
#                 '''check flight'''
#                 pilot.result = verify_track(pilot.track, task)
#                 '''remove pilot from list'''
#                 pilots_list.pop(idx)
#             except IOError:
#                 print(f"Error assigning track {filename} to pilot \n")


# def get_tracks_from_source(task, source=None):
#     """ Accept tracks for unscored pilots of the task
#         - Gets unscored pilots list and, if is not null:
#         - Gets tracks from server source to a temporary folder
#         - assigns tracks to pilots
#         - imports assigned track to correct task folder and, if needed, changes filename"""
#     # TODO function that loads existing results before, so we can score directly after?
#     from tempfile import TemporaryDirectory
#     import importlib
#
#     ''' Get unscored pilots list'''
#     pilots_list = get_unscored_pilots(task.task_id)
#     if len(pilots_list) == 0:
#         print(f"No pilots without tracks found registered to the comp...")
#         return
#
#     ''' load source lib'''
#     if source is None:
#         if task.track_source not in track_sources:
#             print(f"We do not have any zipfile source.")
#             return
#         else:
#             source = importlib.import_module('tracksources.' + task.track_source)
#
#     '''get zipfile'''
#     with TemporaryDirectory() as archive_dir:
#         zipfile = source.get_zipfile(task, archive_dir)
#
#         ''' Get tracks from zipfile to a temporary folder'''
#         with TemporaryDirectory() as temp_dir:
#             extract_tracks(zipfile, temp_dir)
#             assign_tracks(task, temp_dir, pilots_list, source)
#
#
# def get_tracks_from_zipfile(task, zipfile):
#     """ Accept tracks for unscored pilots of the task
#         - Gets unscored pilots list and, if is not null:
#         - Gets tracks from zipfile to a temporary folder
#         - assigns tracks to pilots
#         - imports assigned track to correct task folder and, if needed, changes filename"""
#     # TODO function that loads existing results before, so we can score directly after?
#     from tempfile import TemporaryDirectory
#
#     ''' Get unscored pilots list'''
#     pilots_list = get_unscored_pilots(task.task_id)
#     if len(pilots_list) == 0:
#         print(f"No pilots without tracks found registered to the comp...")
#         return
#
#     ''' Get tracks from zipfile to a temporary folder'''
#     with TemporaryDirectory() as temp_dir:
#         extract_tracks(zipfile, temp_dir)
#         assign_tracks(task, temp_dir, pilots_list, task.track_source)