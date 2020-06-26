"""
Module for mySQL connection using sqlalchemy
Use:    from db.conn import db_session

Airscore
Antonio Golfari, Stuart Mackintosh - 2020
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.scoping import scoped_session
from sqlalchemy import exc
from Defines import MYSQLHOST, DATABASE, MYSQLUSER, MYSQLPASSWORD
from contextlib import contextmanager

'''basic connection'''
host = MYSQLHOST
dbase = DATABASE
user = MYSQLUSER
passwd = MYSQLPASSWORD

connectionString = f'mysql+pymysql://{user}:{passwd}@{host}/{dbase}?charset=utf8mb4'
# engine = create_engine(connectionString,
#                        pool_pre_ping=True,
#                        echo=True)       # pool_pre_ping could be deleted if MySQL is stable
engine = create_engine(connectionString,
                       pool_pre_ping=True,
                       convert_unicode=True)

Session = scoped_session(sessionmaker(autocommit=False,
                                      autoflush=False,
                                      bind=engine))


@contextmanager
def db_session():
    """Provide a transactional scope around a series of operations."""
    session = Session()
    print(f'with session id: {id(session)}')
    try:
        yield session
        session.commit()
    except exc.SQLAlchemyError:
        print('SQLAlchemy Error')
        session.rollback()
        # raise
    except exc.IntegrityError as e:
        print('Integrity Error')
        session.rollback()
    except Exception:
        print('Exception Error')
        session.rollback()
    finally:
        # session.expunge_all()
        # session.close()
        ''''''

# class Database(object):
#     def __str__(self):
#         return "SQLAlchemy DB Connection Object"
#
#     def __init__(self, session=None):
#         self.Base = Base
#         if session is None:
#             self._session = Session()
#             self._ext = False
#         else:
#             self._ext = True
#             self._session = session
#
#     def __enter__(self):
#         return self
#
#     def __exit__(self, exc_type, exc_val, exc_tb):
#         if self._ext:
#             self._session.flush()
#         else:
#             self._session.commit()
#             self._session.close()
#
#     @property
#     def session(self):
#         return self._session
#
#     @property
#     def commit(self):
#         return self._session.commit()
#
#     def populate_obj(self, obj, result):
#         """ Associate query result with class object attributes, using same name
#             Input:
#                 obj     - OBJ: object with attributes to populate with query result
#                 result  - OBJ: query result (should be one row)"""
#
#         '''check if result has one row'''
#         if type(result) == list:
#             result = result[0]
#         for x in obj.__dict__.keys():
#             if hasattr(result, x):
#                 setattr(obj, x, getattr(result, x))
#
#     def populate_row(self, row, obj):
#         """ populate a Table row object from an object
#             Input:
#                 row     - OBJ: Table obj
#                 result  - OBJ: object"""
#         try:
#             for x in row.__table__.columns.keys():
#                 if hasattr(obj, x):
#                     setattr(row, x, getattr(obj, x))
#         except TypeError as e:
#             print(f'Error populating table row: obj is not iterable')
#
#     def as_dict(self, obj):
#         """ as we have still a lot of procedures written for dicts created from
#             old MySQL queries
#             Returns a dict if obj is a single row, or a list of dicts if obj is a list
#         """
#         if type(obj) is list:
#             return [object_to_dict(el) for el in obj]
#         else:
#             return object_to_dict(obj)
#
#
# def get_row(row):
#     from collections import OrderedDict
#     result = OrderedDict()
#     for key in row.__mapper__.c.keys():
#         if getattr(row, key) is not None:
#             result[key] = str(getattr(row, key))
#         else:
#             result[key] = getattr(row, key)
#     return result
#
#
# def get_row_2(row):
#     from sqlalchemy import inspect
#     return {c.key: getattr(row, c.key)
#             for c in inspect(row).mapper.column_attrs}
#
#
# def model_to_dict(obj, visited_children=None, back_relationships=None):
#     from sqlalchemy.orm import class_mapper
#     if visited_children is None:
#         visited_children = set()
#     if back_relationships is None:
#         back_relationships = set()
#     serialized_data = {c.key: getattr(obj, c.key) for c in obj.__table__.columns}
#     relationships = class_mapper(obj.__class__).relationships
#     visitable_relationships = [(name, rel) for name, rel in relationships.items() if name not in back_relationships]
#     for name, relation in visitable_relationships:
#         if relation.backref:
#             back_relationships.add(relation.backref)
#         relationship_children = getattr(obj, name)
#         if relationship_children is not None:
#             if relation.uselist:
#                 children = []
#                 for child in [c for c in relationship_children if c not in visited_children]:
#                     visited_children.add(child)
#                     children.append(model_to_dict(child, visited_children, back_relationships))
#                 serialized_data[name] = children
#             else:
#                 serialized_data[name] = model_to_dict(relationship_children, visited_children, back_relationships)
#     return serialized_data
#
#
# def object_to_dict(obj, found=None):
#     if found is None:
#         found = set()
#     mapper = class_mapper(obj.__class__)
#     columns = [column.key for column in mapper.columns]
#     get_key_value = lambda c: (c, getattr(obj, c).isoformat()) if isinstance(getattr(obj, c), datetime) else (
#         c, getattr(obj, c))
#     out = dict(map(get_key_value, columns))
#     for name, relation in mapper.relationships.items():
#         if relation not in found:
#             found.add(relation)
#             related_obj = getattr(obj, name)
#             if related_obj is not None:
#                 if relation.uselist:
#                     out[name] = [object_to_dict(child, found) for child in related_obj]
#                 else:
#                     out[name] = object_to_dict(related_obj, found)
#     return out
