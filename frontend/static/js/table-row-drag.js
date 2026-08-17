/**
 * 投递表格行拖拽排序（序号列手柄）
 * OfferflowTableDrag.init(container, { onReorder(ids), pinGroup: true })
 */
(function (global) {
  var GRIP_SVG =
    '<svg class="of-row-drag-handle__grip" viewBox="0 0 10 16" fill="currentColor" aria-hidden="true">' +
    '<circle cx="3" cy="3" r="1.2"/><circle cx="7" cy="3" r="1.2"/>' +
    '<circle cx="3" cy="8" r="1.2"/><circle cx="7" cy="8" r="1.2"/>' +
    '<circle cx="3" cy="13" r="1.2"/><circle cx="7" cy="13" r="1.2"/>' +
    '</svg>';

  function seqCellHtml(index) {
    var n = (index | 0) + 1;
    return (
      '<td class="col-num of-drag-cell" onclick="event.stopPropagation()">' +
      '<span class="of-row-drag-handle" draggable="true" role="button" tabindex="0" ' +
      'title="拖动调整顺序" aria-label="拖动第 ' +
      n +
      ' 行排序">' +
      '<span class="of-row-drag-handle__num">' +
      n +
      '</span>' +
      GRIP_SVG +
      '</span></td>'
    );
  }

  function rowPinned(tr) {
    return tr && tr.classList.contains('row-pinned');
  }

  function findScrollRoot(el) {
    var n = el;
    while (n && n !== document.body) {
      try {
        var st = global.getComputedStyle(n);
        var oy = st.overflowY;
        if ((oy === 'auto' || oy === 'scroll') && n.scrollHeight > n.clientHeight + 4) return n;
      } catch (e) { /* ignore */ }
      n = n.parentElement;
    }
    return document.scrollingElement || document.documentElement;
  }

  function updateRowNumbers(tbody) {
    tbody.querySelectorAll('tr[data-id]').forEach(function (tr, idx) {
      var num = tr.querySelector('.of-row-drag-handle__num');
      if (num) num.textContent = String(idx + 1);
      tr.setAttribute('data-row-index', String(idx));
    });
  }

  function clearDropMarks(tbody) {
    tbody.querySelectorAll('.of-row-drop-target--before, .of-row-drop-target--after').forEach(function (tr) {
      tr.classList.remove('of-row-drop-target--before', 'of-row-drop-target--after');
    });
  }

  function clearDraggingRows(root) {
    (root || document).querySelectorAll('tr.of-row--dragging').forEach(function (tr) {
      tr.classList.remove('of-row--dragging');
    });
    (root || document).querySelectorAll('.of-row-drag-handle').forEach(function (h) {
      h.style.cursor = '';
    });
  }

  function endSession(session) {
    if (!session) return;
    clearDraggingRows(session.tbody);
    clearDropMarks(session.tbody);
    if (session.onDocDragOver) {
      document.removeEventListener('dragover', session.onDocDragOver, true);
      session.onDocDragOver = null;
    }
    if (session.onWheel) {
      document.removeEventListener('wheel', session.onWheel, { passive: true, capture: true });
      session.onWheel = null;
    }
    if (session.rafId) {
      cancelAnimationFrame(session.rafId);
      session.rafId = 0;
    }
    session.dragSrc = null;
    session.dropMode = 'before';
  }

  function attachScrollHelpers(session, e) {
    if (!session.scrollRoot || !session.dragSrc) return;
    var rect = session.scrollRoot.getBoundingClientRect();
    var y = e.clientY;
    var edge = 56;
    var speed = 14;
    if (y < rect.top + edge) session.scrollRoot.scrollTop -= speed;
    else if (y > rect.bottom - edge) session.scrollRoot.scrollTop += speed;
  }

  function init(container, options) {
    if (!container) return;
    options = options || {};
    var pinGroup = options.pinGroup !== false;
    var tbody = container.querySelector('tbody');
    if (!tbody) return;

    var session = tbody._ofDragSession;
    if (!session) {
      session = {
        tbody: tbody,
        dragSrc: null,
        dropMode: 'before',
        scrollRoot: findScrollRoot(container),
        onDocDragOver: null,
        onWheel: null,
        rafId: 0,
        options: options,
      };
      tbody._ofDragSession = session;

      session.onDocDragOver = function (e) {
        if (!session.dragSrc) return;
        e.preventDefault();
        attachScrollHelpers(session, e);
      };

      session.onWheel = function (e) {
        if (!session.dragSrc || !session.scrollRoot) return;
        session.scrollRoot.scrollTop += e.deltaY;
      };

      tbody.addEventListener('dragstart', function (e) {
        var handle = e.target.closest('.of-row-drag-handle');
        if (!handle) return;
        var tr = handle.closest('tr[data-id]');
        if (!tr) return;
        e.stopPropagation();
        endSession(session);
        session.dragSrc = tr;
        if (e.dataTransfer) {
          e.dataTransfer.effectAllowed = 'move';
          e.dataTransfer.setData('text/plain', tr.getAttribute('data-id') || '');
          try {
            var img = new Image();
            img.src =
              'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
            e.dataTransfer.setDragImage(img, 0, 0);
          } catch (err) { /* ignore */ }
        }
        tr.classList.add('of-row--dragging');
        handle.style.cursor = 'grabbing';
        document.addEventListener('dragover', session.onDocDragOver, true);
        document.addEventListener('wheel', session.onWheel, { passive: true, capture: true });
      });

      tbody.addEventListener('dragend', function () {
        endSession(session);
      });

      tbody.addEventListener('dragover', function (e) {
        if (!session.dragSrc) return;
        e.preventDefault();
        if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
        attachScrollHelpers(session, e);
        var over = e.target.closest('tr[data-id]');
        clearDropMarks(tbody);
        if (!over || over === session.dragSrc) return;
        if (pinGroup && rowPinned(over) !== rowPinned(session.dragSrc)) return;
        var rect = over.getBoundingClientRect();
        session.dropMode = e.clientY < rect.top + rect.height / 2 ? 'before' : 'after';
        over.classList.add(
          session.dropMode === 'before' ? 'of-row-drop-target--before' : 'of-row-drop-target--after'
        );
      });

      tbody.addEventListener('drop', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var src = session.dragSrc;
        if (!src) {
          endSession(session);
          return;
        }
        var over = e.target.closest('tr[data-id]');
        clearDropMarks(tbody);
        if (over && over !== src) {
          if (pinGroup && rowPinned(over) !== rowPinned(src)) {
            if (typeof toast === 'function') toast('置顶行与普通行请分开排序', 'warning');
          } else {
            if (session.dropMode === 'before') tbody.insertBefore(src, over);
            else tbody.insertBefore(src, over.nextSibling);
            updateRowNumbers(tbody);
            var ids = Array.prototype.map.call(tbody.querySelectorAll('tr[data-id]'), function (tr) {
              return tr.getAttribute('data-id');
            });
            endSession(session);
            if (typeof session.options.onReorder === 'function') {
              session.options.onReorder(ids);
            }
            return;
          }
        }
        endSession(session);
      });
    }

    updateRowNumbers(tbody);
  }

  global.OfferflowTableDrag = {
    init: init,
    seqCellHtml: seqCellHtml,
    clearDraggingRows: clearDraggingRows,
  };
})(typeof window !== 'undefined' ? window : this);
