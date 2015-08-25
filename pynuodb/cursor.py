"""A module for housing the Cursor class.

Exported Classes:

Cursor -- Class for representing a database cursor.

"""

from collections import deque

from .statement import Statement, PreparedStatement
from .exception import Error, NotSupportedError, ProgrammingError


class Cursor(object):

    """Class for representing a database cursor.
    
    Public Functions:
    close -- Closes the cursor into the database.
    callproc -- Currently not supported.
    execute -- Executes an SQL operation.
    executemany -- Executes the operation for each list of paramaters passed in.
    fetchone -- Fetches the first row of results generated by the previous execute.
    fetchmany -- Fetches the number of rows that are passed in.
    fetchall -- Fetches everything generated by the previous execute.
    nextset -- Currently not supported.
    setinputsizes -- Currently not supported.
    setoutputsize -- Currently not supported.
    
    Private Functions:
    __init__ -- Constructor for the Cursor class.
    _check_closed -- Checks if the cursor is closed.
    _reset -- Resets SQL transaction variables.
    _execute -- Handles operations without parameters.
    _executeprepared -- Handles operations with parameters.
    _get_next_results -- Gets the next set of results.    
    """
    
    def __init__(self, session, prepared_statement_cache_size):
        """
        Constructor for the Cursor class.
        :type session EncodedSession
        """
        self.session = session
        """ :type : EncodedSession """

        self._statement_cache = StatementCache(session, prepared_statement_cache_size)
        """ :type : StatementCache """

        self._result_set = None
        """ :type : result_set.ResultSet """

        self.closed = False
        self.arraysize = 1
        
        self.description = None
        self.rowcount = -1
        self.colcount = -1
        self.rownumber = 0
        self.__query = None
        
    @property    
    def query(self):
        """Return the most recent query"""
        return self.__query

    def close(self):
        """Closes the cursor into the database."""
        self._check_closed()
        self._statement_cache.shutdown()
        if self._result_set:
            self._result_set.close(self.session)
        self.closed = True

    def _check_closed(self):
        """Checks if the cursor is closed."""
        if self.closed:
            raise Error("cursor is closed")
        if self.session.closed:
            raise Error("connection is closed")

    def _reset(self):
        """Resets SQL transaction variables."""
        self.description = None
        self.rowcount = -1
        self.colcount = -1
        self._result_set = None

    def callproc(self, procname, parameters=None):
        """Currently not supported."""
        if(procname is not None or parameters is not None):
            raise NotSupportedError("Currently unsupported")

    def execute(self, operation, parameters=None):
        """Executes an SQL operation.
        
        The SQL operations can be with or without parameters, if parameters are included
        then _executeprepared is invoked to prepare and execute the operation.
        
        Arguments:
        operation -- SQL operation to be performed.
        parameters -- Additional parameters for the operation may be supplied, but these
                      are optional.
        
        Returns:
        None
        """
        self._check_closed()
        self._reset()
        self.__query = operation

        if parameters is None:
            exec_result = self._execute(operation)
        else:
            exec_result = self._executeprepared(operation, parameters)

        self.rowcount = exec_result.row_count
        if exec_result.result > 0:
            self._result_set = self.session.fetch_result_set(exec_result.statement)
            self.description = self.session.fetch_result_set_description(self._result_set)

        # TODO: ???
        if self.rowcount < 0:
            self.rowcount = -1
        self.rownumber = 0

    def _execute(self, operation):
        """Handles operations without parameters."""
        # Use handle to query
        return self.session.execute_statement(self._statement_cache.get_statement(), operation)

    def _executeprepared(self, operation, parameters):
        """Handles operations with parameters."""
        # Create a statement handle
        p_statement = self._statement_cache.get_prepared_statement(operation)
        
        if p_statement.parameter_count != len(parameters):
            raise ProgrammingError("Incorrect number of parameters specified, expected %d, got %d" %
                                   (p_statement.parameter_count, len(parameters)))
        
        # Use handle to query
        return self.session.execute_prepared_statement(p_statement, parameters)

    def executemany(self, operation, seq_of_parameters):
        """Executes the operation for each list of paramaters passed in."""
        self._check_closed()

        p_statement = self._statement_cache.get_prepared_statement(operation)
        self.session.execute_batch_prepared_statement(p_statement, seq_of_parameters)

    def fetchone(self):
        """Fetches the first row of results generated by the previous execute."""
        self._check_closed()
        if self._result_set is None:
            raise Error("Previous execute did not produce any results or no call was issued yet")
        self.rownumber += 1
        return self._result_set.fetchone(self.session)

    def fetchmany(self, size=None):
        """Fetches the number of rows that are passed in."""
        self._check_closed()
        
        if size is None:
            size = self.arraysize
            
        fetched_rows = []
        num_fetched_rows = 0
        while num_fetched_rows < size:
            row = self.fetchone()
            if row is None:
                break
            else:
                fetched_rows.append(row)
                num_fetched_rows += 1
        return fetched_rows

    def fetchall(self):
        """Fetches everything generated by the previous execute."""
        self._check_closed()

        fetched_rows = []
        while True:
            row = self.fetchone()
            if row is None:
                break
            else:
                fetched_rows.append(row)
        return fetched_rows   

    def nextset(self):
        """Currently not supported."""
        raise NotSupportedError("Currently unsupported")

    def setinputsizes(self, sizes):
        """Currently not supported."""
        pass

    def setoutputsize(self, size, column=None):
        """Currently not supported."""
        pass


class StatementCache(object):
    def __init__(self, session, prepared_statement_cache_size):
        self._session = session
        """ :type : EncodedSession """

        self._statement = self._session.create_statement()
        """ :type : Statement """

        self._ps_cache = dict()
        """ :type : dict[str,PreparedStatement] """

        self._ps_key_queue = deque()
        """ :type : deque[str] """

        self._ps_cache_size = prepared_statement_cache_size
        """ :type : int """

    def get_statement(self):
        """
        :rtype : Statement
        """
        return self._statement

    def get_prepared_statement(self, query):
        """
        :type query str
        :rtype : PreparedStatement
        """

        statement = self._ps_cache.get(query)
        if statement is not None:
            self._ps_key_queue.remove(query)
            self._ps_key_queue.append(query)
            return statement

        statement = self._session.create_prepared_statement(query)

        while len(self._ps_cache) >= self._ps_cache_size:
            lru_statement_key = self._ps_key_queue.popleft()
            statement_to_remove = self._ps_cache[lru_statement_key]
            self._session.close_statement(statement_to_remove)
            del self._ps_cache[lru_statement_key]

        self._ps_key_queue.append(query)
        self._ps_cache[query] = statement

        return statement

    def shutdown(self):
        """ Close connection and clear the cursor cache"""
        self._session.close_statement(self._statement)

        for key in self._ps_cache:
            statement_to_remove = self._ps_cache[key]
            self._session.close_statement(statement_to_remove)

        self._ps_cache.clear()
        self._ps_key_queue.clear()

