class Game:
    """
    game state and game logic.
    """

    BOARD_SIZE = 8
    WHITE = "white"
    BLACK = "black"

    INITIAL_CASTLING_RIGHTS = {
        WHITE: {"king_side": True, "queen_side": True},
        BLACK: {"king_side": True, "queen_side": True},
    }

    def __init__(self):
        self.board = []
        self.turn = self.WHITE
        self.en_passant_target = None
        self.castling_rights = self._create_initial_castling_rights()
        self.halfmove_clock = 0
        self.position_history = {}
        self.start_game()

    # ---------------- Setup ----------------

    def _create_initial_castling_rights(self):
        return {
            self.WHITE: {"king_side": True, "queen_side": True},
            self.BLACK: {"king_side": True, "queen_side": True},
        }

    def create_initial_board(self):
        return [
            ["bR", "bN", "bB", "bQ", "bK", "bB", "bN", "bR"],
            ["bP", "bP", "bP", "bP", "bP", "bP", "bP", "bP"],
            [None, None, None, None, None, None, None, None],
            [None, None, None, None, None, None, None, None],
            [None, None, None, None, None, None, None, None],
            [None, None, None, None, None, None, None, None],
            ["wP", "wP", "wP", "wP", "wP", "wP", "wP", "wP"],
            ["wR", "wN", "wB", "wQ", "wK", "wB", "wN", "wR"],
        ]

    def start_game(self):
        """Reset the game to the initial position"""
        self.board = self.create_initial_board()
        self.turn = self.WHITE
        self.en_passant_target = None
        self.castling_rights = self._create_initial_castling_rights()
        self.halfmove_clock = 0
        self.position_history = {}
        self._record_current_position()

    # ---------------- Board Access ----------------

    def get_board(self):
        """Return current board state"""
        return self.board

    def get_piece(self, row, col):
        """Return the piece on a square"""
        return self.board[row][col]

    def copy_board(self, board):
        return [row[:] for row in board]

    def copy_castling_rights(self, castling_rights):
        return {
            self.WHITE: {
                "king_side": bool(castling_rights.get(self.WHITE, {}).get("king_side", False)),
                "queen_side": bool(castling_rights.get(self.WHITE, {}).get("queen_side", False)),
            },
            self.BLACK: {
                "king_side": bool(castling_rights.get(self.BLACK, {}).get("king_side", False)),
                "queen_side": bool(castling_rights.get(self.BLACK, {}).get("queen_side", False)),
            },
        }

    def _normalize_en_passant_target_for_position_key(self):
        return self.en_passant_target if self.en_passant_target is not None else None

    def get_position_key(self):
        board_key = tuple(tuple(row) for row in self.board)
        castling_key = (
            self.castling_rights[self.WHITE]["king_side"],
            self.castling_rights[self.WHITE]["queen_side"],
            self.castling_rights[self.BLACK]["king_side"],
            self.castling_rights[self.BLACK]["queen_side"],
        )
        return (
            board_key,
            self.turn,
            self._normalize_en_passant_target_for_position_key(),
            castling_key,
        )

    def _record_current_position(self):
        position_key = self.get_position_key()
        self.position_history[position_key] = self.position_history.get(position_key, 0) + 1

    # ---------------- Basic Helpers ----------------

    def is_within_bounds(self, row, col):
        return 0 <= row < self.BOARD_SIZE and 0 <= col < self.BOARD_SIZE

    def get_piece_color(self, piece):
        if piece is None:
            return None
        return self.WHITE if piece.startswith("w") else self.BLACK

    def get_opponent_color(self, color):
        return self.BLACK if color == self.WHITE else self.WHITE

    def get_piece_type(self, piece):
        if piece is None:
            return None
        return piece[1]

    def get_home_row(self, color):
        return 7 if color == self.WHITE else 0

    # ---------------- Turn Handling ----------------

    def switch_turn(self):
        """Switch active player"""
        self.turn = self.BLACK if self.turn == self.WHITE else self.WHITE

    def get_turn(self):
        return self.turn

    # ---------------- Move Execution ----------------

    def move(self, from_pos, to_pos, promotion_piece_type="Q"):
        """Move a piece from one square to another if the move is legal"""

        if not self.is_legal_move(from_pos, to_pos, promotion_piece_type):
            return False

        from_row, from_col = from_pos
        to_row, to_col = to_pos

        piece = self.board[from_row][from_col]
        target_piece = self.board[to_row][to_col]
        piece_color = self.get_piece_color(piece)

        old_en_passant_target = self.en_passant_target
        was_capture = target_piece is not None
        self.en_passant_target = None

        # En passant capture
        if (
            self.get_piece_type(piece) == "P"
            and old_en_passant_target == (to_row, to_col)
            and target_piece is None
            and from_col != to_col
        ):
            captured_pawn_row = to_row + 1 if piece_color == self.WHITE else to_row - 1
            self.board[captured_pawn_row][to_col] = None
            was_capture = True

        self._move_piece_on_board(self.board, from_pos, to_pos)
        self._apply_castling_rook_move_if_needed(self.board, piece, from_pos, to_pos)

        if self.get_piece_type(piece) == "P" and abs(to_row - from_row) == 2:
            self.en_passant_target = ((from_row + to_row) // 2, from_col)

        self.update_castling_rights_after_move(piece, from_pos, to_pos, target_piece)
        self.promote_pawn_if_needed(to_pos, promotion_piece_type)

        if self.get_piece_type(piece) == "P" or was_capture:
            self.halfmove_clock = 0
        else:
            self.halfmove_clock += 1

        self.switch_turn()
        self._record_current_position()
        return True

    def _move_piece_on_board(self, board, from_pos, to_pos):
        from_row, from_col = from_pos
        to_row, to_col = to_pos
        board[to_row][to_col] = board[from_row][from_col]
        board[from_row][from_col] = None

    def _apply_en_passant_capture_if_needed(self, board, piece, piece_color, from_pos, to_pos, target_piece, en_passant_target):
        from_row, from_col = from_pos
        to_row, to_col = to_pos

        if (
            self.get_piece_type(piece) == "P"
            and en_passant_target == (to_row, to_col)
            and target_piece is None
            and from_col != to_col
        ):
            captured_pawn_row = to_row + 1 if piece_color == self.WHITE else to_row - 1
            board[captured_pawn_row][to_col] = None

    def _apply_castling_rook_move_if_needed(self, board, piece, from_pos, to_pos):
        from_row, from_col = from_pos
        to_row, to_col = to_pos

        if self.get_piece_type(piece) != "K" or abs(to_col - from_col) != 2:
            return

        if to_col == 6:
            rook_from = (from_row, 7)
            rook_to = (from_row, 5)
        else:
            rook_from = (from_row, 0)
            rook_to = (from_row, 3)

        rook_piece = board[rook_from[0]][rook_from[1]]
        board[rook_to[0]][rook_to[1]] = rook_piece
        board[rook_from[0]][rook_from[1]] = None

    # ---------------- King / Attack / Check ----------------

    def find_king(self, color, board=None):
        board = self.board if board is None else board
        king_code = "wK" if color == self.WHITE else "bK"

        for row in range(self.BOARD_SIZE):
            for col in range(self.BOARD_SIZE):
                if board[row][col] == king_code:
                    return row, col
        return None

    def is_square_attacked(self, row, col, by_color, board=None):
        board = self.board if board is None else board

        if self._is_attacked_by_pawn(row, col, by_color, board):
            return True
        if self._is_attacked_by_knight(row, col, by_color, board):
            return True
        if self._is_attacked_by_sliding_piece(row, col, by_color, board, diagonal=True):
            return True
        if self._is_attacked_by_sliding_piece(row, col, by_color, board, diagonal=False):
            return True
        if self._is_attacked_by_king(row, col, by_color, board):
            return True

        return False

    def _is_attacked_by_pawn(self, row, col, by_color, board):
        pawn_direction = -1 if by_color == self.WHITE else 1
        pawn_code = "wP" if by_color == self.WHITE else "bP"

        pawn_attack_row = row - pawn_direction
        for pawn_col in (col - 1, col + 1):
            if self.is_within_bounds(pawn_attack_row, pawn_col) and board[pawn_attack_row][pawn_col] == pawn_code:
                return True
        return False

    def _is_attacked_by_knight(self, row, col, by_color, board):
        knight_code = "wN" if by_color == self.WHITE else "bN"
        knight_offsets = [
            (-2, -1), (-2, 1), (-1, -2), (-1, 2),
            (1, -2), (1, 2), (2, -1), (2, 1),
        ]

        for dr, dc in knight_offsets:
            r = row + dr
            c = col + dc
            if self.is_within_bounds(r, c) and board[r][c] == knight_code:
                return True
        return False

    def _is_attacked_by_sliding_piece(self, row, col, by_color, board, diagonal):
        if diagonal:
            directions = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
            valid_attackers = (
                "wB", "wQ") if by_color == self.WHITE else ("bB", "bQ")
        else:
            directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
            valid_attackers = (
                "wR", "wQ") if by_color == self.WHITE else ("bR", "bQ")

        for dr, dc in directions:
            r = row + dr
            c = col + dc
            while self.is_within_bounds(r, c):
                piece = board[r][c]
                if piece is not None:
                    if piece in valid_attackers:
                        return True
                    break
                r += dr
                c += dc

        return False

    def _is_attacked_by_king(self, row, col, by_color, board):
        king_code = "wK" if by_color == self.WHITE else "bK"

        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                r = row + dr
                c = col + dc
                if self.is_within_bounds(r, c) and board[r][c] == king_code:
                    return True

        return False

    def is_in_check(self, color, board=None):
        board = self.board if board is None else board
        king_pos = self.find_king(color, board)
        if king_pos is None:
            return False

        opponent_color = self.get_opponent_color(color)
        return self.is_square_attacked(king_pos[0], king_pos[1], opponent_color, board)

    # ---------------- Move Simulation ----------------

    def simulate_move(self, from_pos, to_pos, promotion_piece_type="Q"):
        simulated_board = self.copy_board(self.board)

        from_row, from_col = from_pos
        to_row, to_col = to_pos

        piece = simulated_board[from_row][from_col]
        target_piece = simulated_board[to_row][to_col]

        if piece is None:
            return simulated_board

        piece_color = self.get_piece_color(piece)

        self._apply_en_passant_capture_if_needed(
            board=simulated_board,
            piece=piece,
            piece_color=piece_color,
            from_pos=from_pos,
            to_pos=to_pos,
            target_piece=target_piece,
            en_passant_target=self.en_passant_target,
        )

        self._move_piece_on_board(simulated_board, from_pos, to_pos)
        self._apply_castling_rook_move_if_needed(simulated_board, piece, from_pos, to_pos)
        self._apply_pawn_promotion_on_board(simulated_board, to_pos, promotion_piece_type)

        return simulated_board

    def _apply_pawn_promotion_on_board(self, board, pos, promotion_piece_type="Q"):
        row, col = pos
        piece = board[row][col]

        if piece not in ("wP", "bP"):
            return

        promotion_piece_type = (promotion_piece_type or "Q").upper()
        if promotion_piece_type not in ("Q", "R", "B", "N"):
            promotion_piece_type = "Q"

        if piece == "wP" and row == 0:
            board[row][col] = f"w{promotion_piece_type}"
        elif piece == "bP" and row == 7:
            board[row][col] = f"b{promotion_piece_type}"

    # ---------------- Castling Rights ----------------

    def update_castling_rights_after_move(self, piece, from_pos, to_pos, captured_piece):
        to_row, to_col = to_pos
        piece_color = self.get_piece_color(piece)

        if self.get_piece_type(piece) == "K":
            self.castling_rights[piece_color]["king_side"] = False
            self.castling_rights[piece_color]["queen_side"] = False

        if self.get_piece_type(piece) == "R":
            self._disable_castling_rights_for_rook_move(piece_color, from_pos)

        self._disable_castling_rights_for_rook_capture(captured_piece, (to_row, to_col))

    def _disable_castling_rights_for_rook_move(self, piece_color, from_pos):
        if piece_color == self.WHITE and from_pos == (7, 0):
            self.castling_rights[self.WHITE]["queen_side"] = False
        elif piece_color == self.WHITE and from_pos == (7, 7):
            self.castling_rights[self.WHITE]["king_side"] = False
        elif piece_color == self.BLACK and from_pos == (0, 0):
            self.castling_rights[self.BLACK]["queen_side"] = False
        elif piece_color == self.BLACK and from_pos == (0, 7):
            self.castling_rights[self.BLACK]["king_side"] = False

    def _disable_castling_rights_for_rook_capture(self, captured_piece, to_pos):
        if captured_piece == "wR":
            if to_pos == (7, 0):
                self.castling_rights[self.WHITE]["queen_side"] = False
            elif to_pos == (7, 7):
                self.castling_rights[self.WHITE]["king_side"] = False
        elif captured_piece == "bR":
            if to_pos == (0, 0):
                self.castling_rights[self.BLACK]["queen_side"] = False
            elif to_pos == (0, 7):
                self.castling_rights[self.BLACK]["king_side"] = False

    def promote_pawn_if_needed(self, pos, promotion_piece_type="Q"):
        self._apply_pawn_promotion_on_board(self.board, pos, promotion_piece_type)

    def is_fifty_move_rule_reached(self):
        return self.halfmove_clock >= 100

    def is_threefold_repetition(self):
        position_key = self.get_position_key()
        return self.position_history.get(position_key, 0) >= 3

    def _get_all_pieces(self):
        pieces = []
        for row in self.board:
            for piece in row:
                if piece is not None:
                    pieces.append(piece)
        return pieces

    def is_insufficient_material(self):
        pieces = self._get_all_pieces()
        non_king_pieces = [piece for piece in pieces if self.get_piece_type(piece) != "K"]

        if not non_king_pieces:
            return True

        if len(non_king_pieces) == 1:
            return self.get_piece_type(non_king_pieces[0]) in ("B", "N")

        if len(non_king_pieces) == 2:
            piece_types = sorted(self.get_piece_type(piece) for piece in non_king_pieces)
            piece_colors = [self.get_piece_color(piece) for piece in non_king_pieces]

            if piece_types == ["B", "B"] and piece_colors[0] != piece_colors[1]:
                bishop_squares = []
                for row in range(self.BOARD_SIZE):
                    for col in range(self.BOARD_SIZE):
                        piece = self.board[row][col]
                        if piece is not None and self.get_piece_type(piece) == "B":
                            bishop_squares.append((row, col))
                if len(bishop_squares) == 2:
                    first_color = (bishop_squares[0][0] + bishop_squares[0][1]) % 2
                    second_color = (bishop_squares[1][0] + bishop_squares[1][1]) % 2
                    return first_color == second_color

        return False

    def can_castle_king_side(self, color):
        row = self.get_home_row(color)
        king = "wK" if color == self.WHITE else "bK"
        rook = "wR" if color == self.WHITE else "bR"
        opponent = self.get_opponent_color(color)

        if not self.castling_rights[color]["king_side"]:
            return False
        if self.board[row][4] != king or self.board[row][7] != rook:
            return False
        if self.board[row][5] is not None or self.board[row][6] is not None:
            return False
        if self.is_in_check(color):
            return False
        if self.is_square_attacked(row, 5, opponent) or self.is_square_attacked(row, 6, opponent):
            return False

        return True

    def can_castle_queen_side(self, color):
        row = self.get_home_row(color)
        king = "wK" if color == self.WHITE else "bK"
        rook = "wR" if color == self.WHITE else "bR"
        opponent = self.get_opponent_color(color)

        if not self.castling_rights[color]["queen_side"]:
            return False
        if self.board[row][4] != king or self.board[row][0] != rook:
            return False
        if self.board[row][1] is not None or self.board[row][2] is not None or self.board[row][3] is not None:
            return False
        if self.is_in_check(color):
            return False
        if self.is_square_attacked(row, 3, opponent) or self.is_square_attacked(row, 2, opponent):
            return False

        return True

    # ---------------- Game Status ----------------

    def has_any_legal_moves(self, color):
        original_turn = self.turn
        self.turn = color

        try:
            for from_row in range(self.BOARD_SIZE):
                for from_col in range(self.BOARD_SIZE):
                    piece = self.board[from_row][from_col]
                    if piece is None or self.get_piece_color(piece) != color:
                        continue

                    for to_row in range(self.BOARD_SIZE):
                        for to_col in range(self.BOARD_SIZE):
                            if self.is_legal_move((from_row, from_col), (to_row, to_col)):
                                return True
            return False
        finally:
            self.turn = original_turn

    def is_checkmate(self, color=None):
        color = self.turn if color is None else color
        return self.is_in_check(color) and not self.has_any_legal_moves(color)

    def is_stalemate(self, color=None):
        color = self.turn if color is None else color

        if self.is_fifty_move_rule_reached():
            return True
        if self.is_threefold_repetition():
            return True
        if self.is_insufficient_material():
            return True

        return not self.is_in_check(color) and not self.has_any_legal_moves(color)

    def get_game_status(self):
        if self.is_checkmate(self.WHITE):
            return "checkmate_black_wins"
        if self.is_checkmate(self.BLACK):
            return "checkmate_white_wins"
        if self.is_fifty_move_rule_reached():
            return "draw_fifty_move_rule"
        if self.is_threefold_repetition():
            return "draw_threefold_repetition"
        if self.is_insufficient_material():
            return "draw_insufficient_material"
        if self.is_stalemate(self.WHITE) or self.is_stalemate(self.BLACK):
            return "stalemate"
        if self.is_in_check(self.turn):
            return f"check_{self.turn}"
        return "ongoing"

    def is_game_over(self):
        return (
            self.is_checkmate(self.WHITE)
            or self.is_checkmate(self.BLACK)
            or self.is_fifty_move_rule_reached()
            or self.is_threefold_repetition()
            or self.is_insufficient_material()
            or self.is_stalemate(self.WHITE)
            or self.is_stalemate(self.BLACK)
        )

    # ---------------- Path Helpers ----------------

    def is_path_clear_straight(self, from_pos, to_pos):
        from_row, from_col = from_pos
        to_row, to_col = to_pos

        if from_row == to_row:
            step = 1 if to_col > from_col else -1
            for col in range(from_col + step, to_col, step):
                if self.board[from_row][col] is not None:
                    return False
            return True

        if from_col == to_col:
            step = 1 if to_row > from_row else -1
            for row in range(from_row + step, to_row, step):
                if self.board[row][from_col] is not None:
                    return False
            return True

        return False

    def is_path_clear_diagonal(self, from_pos, to_pos):
        from_row, from_col = from_pos
        to_row, to_col = to_pos

        row_diff = to_row - from_row
        col_diff = to_col - from_col

        if abs(row_diff) != abs(col_diff):
            return False

        row_step = 1 if row_diff > 0 else -1
        col_step = 1 if col_diff > 0 else -1

        row = from_row + row_step
        col = from_col + col_step

        while row != to_row and col != to_col:
            if self.board[row][col] is not None:
                return False
            row += row_step
            col += col_step

        return True

    # ---------------- Piece Move Validation ----------------

    def is_legal_pawn_move(self, from_pos, to_pos, piece, target_piece):
        from_row, from_col = from_pos
        to_row, to_col = to_pos

        direction = -1 if piece.startswith("w") else 1
        start_row = 6 if piece.startswith("w") else 1

        row_diff = to_row - from_row
        col_diff = to_col - from_col

        if col_diff == 0:
            if target_piece is not None:
                return False
            if row_diff == direction:
                return True
            if from_row == start_row and row_diff == 2 * direction:
                intermediate_row = from_row + direction
                return self.board[intermediate_row][from_col] is None
            return False

        if abs(col_diff) == 1 and row_diff == direction:
            if target_piece is not None:
                return self.get_piece_color(target_piece) != self.get_piece_color(piece)
            return self.en_passant_target == (to_row, to_col)

        return False

    def is_legal_rook_move(self, from_pos, to_pos):
        from_row, from_col = from_pos
        to_row, to_col = to_pos
        if from_row != to_row and from_col != to_col:
            return False
        return self.is_path_clear_straight(from_pos, to_pos)

    def is_legal_bishop_move(self, from_pos, to_pos):
        from_row, from_col = from_pos
        to_row, to_col = to_pos
        if abs(to_row - from_row) != abs(to_col - from_col):
            return False
        return self.is_path_clear_diagonal(from_pos, to_pos)

    def is_legal_knight_move(self, from_pos, to_pos):
        from_row, from_col = from_pos
        to_row, to_col = to_pos
        row_diff = abs(to_row - from_row)
        col_diff = abs(to_col - from_col)
        return (row_diff, col_diff) in [(2, 1), (1, 2)]

    def is_legal_queen_move(self, from_pos, to_pos):
        return self.is_legal_rook_move(from_pos, to_pos) or self.is_legal_bishop_move(from_pos, to_pos)

    def is_legal_king_move(self, from_pos, to_pos):
        from_row, from_col = from_pos
        to_row, to_col = to_pos

        row_diff = abs(to_row - from_row)
        col_diff = abs(to_col - from_col)

        if max(row_diff, col_diff) == 1:
            return True

        piece = self.board[from_row][from_col]
        color = self.get_piece_color(piece)

        if row_diff == 0 and col_diff == 2:
            if to_col == 6:
                return self.can_castle_king_side(color)
            if to_col == 2:
                return self.can_castle_queen_side(color)

        return False

    def _is_basic_piece_move_legal(self, piece_type, from_pos, to_pos, piece, target_piece):
        if piece_type == "P":
            return self.is_legal_pawn_move(from_pos, to_pos, piece, target_piece)
        if piece_type == "R":
            return self.is_legal_rook_move(from_pos, to_pos)
        if piece_type == "B":
            return self.is_legal_bishop_move(from_pos, to_pos)
        if piece_type == "N":
            return self.is_legal_knight_move(from_pos, to_pos)
        if piece_type == "Q":
            return self.is_legal_queen_move(from_pos, to_pos)
        if piece_type == "K":
            return self.is_legal_king_move(from_pos, to_pos)
        return False

    def is_legal_move(self, from_pos, to_pos, promotion_piece_type="Q"):
        from_row, from_col = from_pos
        to_row, to_col = to_pos

        if not self.is_within_bounds(from_row, from_col) or not self.is_within_bounds(to_row, to_col):
            return False

        if from_pos == to_pos:
            return False

        piece = self.board[from_row][from_col]
        target_piece = self.board[to_row][to_col]

        if piece is None:
            return False

        piece_color = self.get_piece_color(piece)
        if piece_color != self.turn:
            return False

        if target_piece is not None and self.get_piece_color(target_piece) == piece_color:
            return False

        piece_type = self.get_piece_type(piece)
        if not self._is_basic_piece_move_legal(piece_type, from_pos, to_pos, piece, target_piece):
            return False

        simulated_board = self.simulate_move(from_pos, to_pos, promotion_piece_type)
        return not self.is_in_check(piece_color, simulated_board)

    # ---------------- Debug ----------------

    def print_board(self):
        """Print board to console for debugging"""
        for row in self.board:
            print(row)
        print()