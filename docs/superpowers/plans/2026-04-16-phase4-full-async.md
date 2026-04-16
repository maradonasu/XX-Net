# Phase 4 Full Async Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create fully async versions of base_container.py and proxy_session.py, replacing threading/selector with asyncio.

**Architecture:** 
- Create new async modules (async_base_container.py, async_proxy_session.py)
- Keep sync versions as fallback
- Use asyncio.StreamReader/StreamWriter for socket I/O
- Use asyncio.Lock/Event/Queue for synchronization

**Tech Stack:** asyncio, asyncio.selector_events, threading → asyncio.Task

---

## Dependency Analysis

### Current Architecture (Threading/Selector)

```
proxy_session.py (1415 lines)
├── threading.Thread: round_trip_worker, timeout_checker
├── threading.Lock: self.lock, get_data_lock
├── base_container.WaitQueue (Condition + Lock)
├── base_container.SendBuffer
├── base_container.BlockReceivePool
└── base_container.ConnectionPipe
    ├── selectors.DefaultSelector
    ├── threading.Thread: pipe_worker
    └── base_container.Conn
        └── socket + threading.Lock
```

### Target Architecture (Asyncio)

```
async_proxy_session.py
├── asyncio.Task: round_trip_worker, timeout_checker
├── asyncio.Lock: self.lock, get_data_lock
├── async_base_container.AsyncWaitQueue (Event)
├── async_base_container.AsyncSendBuffer
├── async_base_container.AsyncBlockReceivePool
└── async_base_container.AsyncConnectionPipe
    ├── asyncio selector (built-in)
    ├── asyncio.Task: pipe_worker
    └── async_base_container.AsyncConn
        └── asyncio.StreamReader/StreamWriter
```

---

## Task 1: Create async_base_container.py

**Files:**
- Create: `code/default/x_tunnel/local/async_base_container.py`
- Test: `code/default/lib/tests/test_async_base_container.py`

### 1.1: Create AsyncWaitQueue

- [ ] **Step 1: Write AsyncWaitQueue class**

```python
class AsyncWaitQueue:
    def __init__(self) -> None:
        self._event: asyncio.Event = asyncio.Event()
        self._running: bool = True
    
    async def wait(self, timeout: Optional[float] = None) -> bool:
        try:
            if timeout:
                await asyncio.wait_for(self._event.wait(), timeout)
            else:
                await self._event.wait()
            return True
        except asyncio.TimeoutError:
            return False
    
    def notify(self) -> None:
        self._event.set()
        self._event.clear()
    
    def stop(self) -> None:
        self._running = False
        self._event.set()
```

- [ ] **Step 2: Write failing test**

```python
class TestAsyncWaitQueue(TestCase):
    def test_wait_and_notify(self):
        import async_loop
        from x_tunnel.local.async_base_container import AsyncWaitQueue
        
        async def do_test():
            q = AsyncWaitQueue()
            results = []
            
            async def waiter():
                await q.wait()
                results.append("done")
            
            task = asyncio.create_task(waiter())
            await asyncio.sleep(0.1)
            self.assertEqual(results, [])
            q.notify()
            await asyncio.sleep(0.1)
            self.assertEqual(results, ["done"])
        
        async_loop.run_async(do_test(), timeout=5)
```

- [ ] **Step 3: Run test to verify it fails**

- [ ] **Step 4: Implement and verify pass**

- [ ] **Step 5: Commit (after user approval)**

---

### 1.2: Create AsyncSendBuffer

- [ ] **Step 1: Write AsyncSendBuffer class (adapt from SendBuffer)**

```python
class AsyncSendBuffer:
    def __init__(self, max_payload: int = 65536) -> None:
        self.max_payload: int = max_payload
        self.pool_size: int = 0
        self._buffer: bytearray = bytearray()
        self._lock: asyncio.Lock = asyncio.Lock()
    
    async def add(self, data: bytes) -> None:
        async with self._lock:
            self._buffer.extend(data)
            self.pool_size = len(self._buffer)
    
    async def get_payload(self) -> Optional[bytes]:
        async with self._lock:
            if len(self._buffer) == 0:
                return None
            payload = bytes(self._buffer[:self.max_payload])
            self._buffer = self._buffer[self.max_payload:]
            self.pool_size = len(self._buffer)
            return payload
    
    async def reset(self) -> None:
        async with self._lock:
            self._buffer = bytearray()
            self.pool_size = 0
```

- [ ] **Step 2: Add test**

- [ ] **Step 3: Verify**

---

### 1.3: Create AsyncConnectionPipe

- [ ] **Step 1: Write AsyncConnectionPipe class**

This is the core class that replaces selector-based pipe_worker with asyncio.

```python
class AsyncConnectionPipe:
    def __init__(self, session: Any, xlog: Any) -> None:
        self.session = session
        self.xlog = xlog
        self.running: bool = True
        self._tasks: Dict[int, asyncio.Task] = {}
        self._sock_conn_map: Dict[int, Any] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
    
    async def add_sock_event(self, sock: socket.socket, conn: Any) -> None:
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        
        def protocol_factory():
            return asyncio.StreamReaderProtocol(reader)
        
        transport, protocol = await loop.connect_accepted_socket(
            protocol_factory, sock=sock
        )
        writer = asyncio.StreamWriter(transport, protocol, reader, loop)
        
        async with self._lock:
            conn._reader = reader
            conn._writer = writer
            self._sock_conn_map[conn.conn_id] = conn
            
            task = asyncio.create_task(self._conn_reader(conn))
            self._tasks[conn.conn_id] = task
    
    async def _conn_reader(self, conn: Any) -> None:
        try:
            while conn.running and self.running:
                data = await conn._reader.read(65536)
                if not data:
                    break
                await conn.on_data_received(data)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.xlog.debug("conn_reader %d error: %r", conn.conn_id, e)
        finally:
            await conn.stop_async()
    
    async def remove_sock(self, conn_id: int) -> None:
        async with self._lock:
            if conn_id in self._tasks:
                self._tasks[conn_id].cancel()
                del self._tasks[conn_id]
            if conn_id in self._sock_conn_map:
                del self._sock_conn_map[conn_id]
    
    async def stop(self) -> None:
        self.running = False
        async with self._lock:
            for task in self._tasks.values():
                task.cancel()
            self._tasks.clear()
            self._sock_conn_map.clear()
```

- [ ] **Step 2: Add test**

- [ ] **Step 3: Verify**

---

### 1.4: Create AsyncConn

- [ ] **Step 1: Write AsyncConn class**

```python
class AsyncConn:
    def __init__(self, session: Any, conn_id: int, sock: socket.socket,
                 host: str, port: int, xlog: Any) -> None:
        self.host = host
        self.port = port
        self.session = session
        self.conn_id = conn_id
        self.sock = sock
        self.xlog = xlog
        
        self.running: bool = True
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock: asyncio.Lock = asyncio.Lock()
        
        self.send_buffer: bytearray = bytearray()
        self.received_position: int = 0
        self.remote_acked_position: int = 0
        self.sended_position: int = 0
    
    async def start(self) -> None:
        await self.session.connection_pipe.add_sock_event(self.sock, self)
    
    async def send(self, data: bytes) -> None:
        if self._writer:
            self._writer.write(data)
            await self._writer.drain()
    
    async def on_data_received(self, data: bytes) -> None:
        await self.session.on_conn_data(self.conn_id, data)
    
    async def stop_async(self, reason: str = "") -> None:
        self.running = False
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        await self.session.remove_conn_async(self.conn_id)
```

- [ ] **Step 2: Add test**

- [ ] **Step 3: Verify**

---

## Task 2: Create async_proxy_session.py

**Files:**
- Create: `code/default/x_tunnel/local/async_proxy_session.py`
- Test: `code/default/lib/tests/test_async_proxy_session.py`

### 2.1: Create AsyncProxySession skeleton

- [ ] **Step 1: Write AsyncProxySession class structure**

```python
class AsyncProxySession:
    def __init__(self) -> None:
        self.config = g.config
        self.wait_queue = AsyncWaitQueue()
        self.send_buffer = AsyncSendBuffer(max_payload=g.config.max_payload)
        self.connection_pipe = AsyncConnectionPipe(self, xlog)
        self.lock: asyncio.Lock = asyncio.Lock()
        
        self.running: bool = False
        self._tasks: List[asyncio.Task] = []
        self.session_id: bytes = utils.generate_random_lowercase(8)
        self.conn_list: Dict[int, AsyncConn] = {}
        self.last_conn_id: int = 0
    
    async def start(self) -> bool:
        async with self.lock:
            if self.running:
                return True
            
            if not await self.login_session():
                return False
            
            self.running = True
            
            for i in range(g.config.concurent_thread_num):
                task = asyncio.create_task(self.round_trip_worker(i))
                self._tasks.append(task)
            
            task = asyncio.create_task(self.timeout_checker())
            self._tasks.append(task)
            
            await self.connection_pipe.start()
            return True
    
    async def stop(self) -> None:
        if not self.running:
            return
        
        self.running = False
        async with self.lock:
            for task in self._tasks:
                task.cancel()
            self._tasks.clear()
            
            await self.close_all_connections()
            await self.send_buffer.reset()
            self.wait_queue.stop()
            await self.connection_pipe.stop()
    
    async def round_trip_worker(self, worker_id: int) -> None:
        while self.running:
            await self.wait_queue.wait(timeout=1)
            if not self.running:
                break
            
            payload = await self.send_buffer.get_payload()
            if payload:
                await self._send_round_trip(payload)
    
    async def timeout_checker(self) -> None:
        while self.running:
            await asyncio.sleep(2)
            await self._check_transfers_timeout()
    
    async def create_conn(self, sock: socket.socket, host: str, port: int) -> Optional[int]:
        async with self.lock:
            conn_id = self.last_conn_id + 1
            self.last_conn_id = conn_id
            
            conn = AsyncConn(self, conn_id, sock, host, port, xlog)
            self.conn_list[conn_id] = conn
            
        await conn.start()
        return conn_id
    
    async def remove_conn_async(self, conn_id: int) -> None:
        async with self.lock:
            if conn_id in self.conn_list:
                del self.conn_list[conn_id]
```

- [ ] **Step 2: Add basic test**

```python
class TestAsyncProxySession(TestCase):
    def test_session_init(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession
        import async_loop
        
        async def do_test():
            session = AsyncProxySession()
            self.assertFalse(session.running)
        
        async_loop.run_async(do_test(), timeout=5)
```

- [ ] **Step 3: Verify import works**

---

## Task 3: Integrate into async_client.py

**Files:**
- Modify: `code/default/x_tunnel/local/async_client.py`

### 3.1: Replace ProxySession with AsyncProxySession

- [ ] **Step 1: Update import**

```python
from .async_proxy_session import AsyncProxySession
```

- [ ] **Step 2: Replace sync executor call with async**

```python
# Before:
g.session = await loop.run_in_executor(None, proxy_session.ProxySession)

# After:
g.session = AsyncProxySession()
await g.session.start()
```

- [ ] **Step 3: Update _handle_connect**

```python
async def _handle_connect(self, host: str, port: int) -> None:
    if not g.session:
        ...
    
    await g.session.login_session()
    
    if not g.session.running:
        ...
    
    # Use async create_conn
    conn_id = await g.session.create_conn(remote_sock, host, port)
```

- [ ] **Step 4: Run full test suite**

- [ ] **Step 5: Manual async mode test**

---

## Task 4: Final Verification

### 4.1: Run complete test suite

- [ ] **Step 1: Run all tests**

```bash
pytest code/default/lib/tests code/default/x_tunnel/tests -q
```

Expected: All tests pass

- [ ] **Step 2: Run async mode SOCKS5 test**

```bash
set XXNET_ASYNC=1
python code/default/x_tunnel/local/async_client.py
curl --socks5 127.0.0.1:1080 https://github.com -v
```

Expected: HTTP 200

- [ ] **Step 3: Compare sync vs async performance**

---

## Risk Assessment

| Component | Risk | Mitigation |
|-----------|------|------------|
| AsyncConnectionPipe | High - replaces selector | Keep sync version as fallback |
| AsyncConn socket handling | Medium - stream protocol | Extensive testing |
| AsyncProxySession state machine | Very High - complex logic | Incremental migration, keep sync working |
| asyncio.Lock vs threading.Lock | Low - similar semantics | Direct replacement |

---

## Estimated Effort

| Task | Lines | Hours |
|------|-------|-------|
| AsyncWaitQueue | ~30 | 0.5 |
| AsyncSendBuffer | ~50 | 0.5 |
| AsyncConnectionPipe | ~150 | 2 |
| AsyncConn | ~100 | 1.5 |
| AsyncProxySession | ~800 | 4 |
| Integration | ~100 | 1 |
| Testing | - | 2 |
| **Total** | ~1230 | **11.5** |

---

## Execution Order

1. Create async_base_container.py with tests
2. Create async_proxy_session.py skeleton
3. Incrementally implement AsyncProxySession methods
4. Integrate into async_client.py
5. Full test verification
6. Request user approval before committing