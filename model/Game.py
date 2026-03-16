class Game:
    """
    game state and game logic.
    """

    def __init__(self):
        self.board = []
        self.turn = "white"
        self.en_passant_target = None
        self.castling_rights = {
            "white": {"king_side": True, "queen_side": True},
            "black": {"king_side": True, "queen_side": True},
        }
        self.start_game()

    # ---------------- Board Setup ----------------

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
        self.turn = "white"
        self.en_passant_target = None
        self.castling_rights = {
            "white": {"king_side": True, "queen_side": True},
            "black": {"king_side": True, "queen_side": True},
        }

    # ---------------- Board Access (getters for Board and Piece) ----------------

    def get_board(self):
        """Return current board state"""
        return self.board

    def get_piece(self, row, col):
        """Return the piece on a square"""
        return self.board[row][col]

    # ---------------- Moves ----------------

    def move(self, from_pos, to_pos):
        """Move a piece from one square to another if the move is legal"""

        if not self.is_legal_move(from_pos, to_pos):
            return False

        from_row, from_col = from_pos
        to_row, to_col = to_pos
        piece = self.board[from_row][from_col]
        target_piece = self.board[to_row][to_col]
        piece_color = self.get_piece_color(piece)

        old_en_passant_target = self.en_passant_target
        self.en_passant_target = None

        if piece[1] == "P" and old_en_passant_target == (to_row, to_col) and target_piece is None and from_col != to_col:
            captured_pawn_row = to_row + 1 if piece_color == "white" else to_row - 1
            self.board[captured_pawn_row][to_col] = None

        self.board[to_row][to_col] = piece
        self.board[from_row][from_col] = None

        if piece[1] == "K" and abs(to_col - from_col) == 2:
            if to_col == 6:
                rook_from = (from_row, 7)
                rook_to = (from_row, 5)
            else:
                rook_from = (from_row, 0)
                rook_to = (from_row, 3)

            rook_piece = self.board[rook_from[0]][rook_from[1]]
            self.board[rook_to[0]][rook_to[1]] = rook_piece
            self.board[rook_from[0]][rook_from[1]] = None

        if piece[1] == "P" and abs(to_row - from_row) == 2:
            self.en_passant_target = ((from_row + to_row) // 2, from_col)

        self.update_castling_rights_after_move(piece, from_pos, to_pos, target_piece)
        self.promote_pawn_if_needed(to_pos)

        self.switch_turn()
        return True

    def copy_board(self, board):
        return [row[:] for row in board]

    def find_king(self, color, board=None):
        board = self.board if board is None else board
        king_code = "wK" if color == "white" else "bK"
        for row in range(8):
            for col in range(8):
                if board[row][col] == king_code:
                    return row, col
        return None

    def is_square_attacked(self, row, col, by_color, board=None):
        board = self.board if board is None else board
        pawn_direction = -1 if by_color == "white" else 1
        pawn_code = "wP" if by_color == "white" else "bP"
        knight_code = "wN" if by_color == "white" else "bN"
        bishop_code = "wB" if by_color == "white" else "bB"
        rook_code = "wR" if by_color == "white" else "bR"
        queen_code = "wQ" if by_color == "white" else "bQ"
        king_code = "wK" if by_color == "white" else "bK"

        pawn_attack_row = row - pawn_direction
        for pawn_col in (col - 1, col + 1):
            if self.is_within_bounds(pawn_attack_row, pawn_col) and board[pawn_attack_row][pawn_col] == pawn_code:
                return True

        knight_offsets = [
            (-2, -1), (-2, 1), (-1, -2), (-1, 2),
            (1, -2), (1, 2), (2, -1), (2, 1),
        ]
        for dr, dc in knight_offsets:
            r = row + dr
            c = col + dc
            if self.is_within_bounds(r, c) and board[r][c] == knight_code:
                return True

        diagonal_directions = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        for dr, dc in diagonal_directions:
            r = row + dr
            c = col + dc
            while self.is_within_bounds(r, c):
                piece = board[r][c]
                if piece is not None:
                    if piece in (bishop_code, queen_code):
                        return True
                    break
                r += dr
                c += dc

        straight_directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        for dr, dc in straight_directions:
            r = row + dr
            c = col + dc
            while self.is_within_bounds(r, c):
                piece = board[r][c]
                if piece is not None:
                    if piece in (rook_code, queen_code):
                        return True
                    break
                r += dr
                c += dc

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
        opponent_color = "black" if color == "white" else "white"
        return self.is_square_attacked(king_pos[0], king_pos[1], opponent_color, board)

    def simulate_move(self, from_pos, to_pos):
        simulated_board = self.copy_board(self.board)
        from_row, from_col = from_pos
        to_row, to_col = to_pos
        piece = simulated_board[from_row][from_col]
        target_piece = simulated_board[to_row][to_col]

        if piece is None:
            return simulated_board

        piece_color = self.get_piece_color(piece)

        if piece[1] == "P" and self.en_passant_target == (to_row, to_col) and target_piece is None and from_col != to_col:
            captured_pawn_row = to_row + 1 if piece_color == "white" else to_row - 1
            simulated_board[captured_pawn_row][to_col] = None

        simulated_board[to_row][to_col] = piece
        simulated_board[from_row][from_col] = None

        if piece[1] == "K" and abs(to_col - from_col) == 2:
            if to_col == 6:
                rook_from = (from_row, 7)
                rook_to = (from_row, 5)
            else:
                rook_from = (from_row, 0)
                rook_to = (from_row, 3)

            rook_piece = simulated_board[rook_from[0]][rook_from[1]]
            simulated_board[rook_to[0]][rook_to[1]] = rook_piece
            simulated_board[rook_from[0]][rook_from[1]] = None

        if piece[1] == "P":
            if piece_color == "white" and to_row == 0:
                simulated_board[to_row][to_col] = "wQ"
            elif piece_color == "black" and to_row == 7:
                simulated_board[to_row][to_col] = "bQ"

        return simulated_board

    def update_castling_rights_after_move(self, piece, from_pos, to_pos, captured_piece):
        from_row, from_col = from_pos
        to_row, to_col = to_pos
        piece_color = self.get_piece_color(piece)
        opponent_color = "black" if piece_color == "white" else "white"

        if piece[1] == "K":
            self.castling_rights[piece_color]["king_side"] = False
            self.castling_rights[piece_color]["queen_side"] = False

        if piece[1] == "R":
            if piece_color == "white" and from_pos == (7, 0):
                self.castling_rights["white"]["queen_side"] = False
            elif piece_color == "white" and from_pos == (7, 7):
                self.castling_rights["white"]["king_side"] = False
            elif piece_color == "black" and from_pos == (0, 0):
                self.castling_rights["black"]["queen_side"] = False
            elif piece_color == "black" and from_pos == (0, 7):
                self.castling_rights["black"]["king_side"] = False

        if captured_piece == "wR":
            if (to_row, to_col) == (7, 0):
                self.castling_rights["white"]["queen_side"] = False
            elif (to_row, to_col) == (7, 7):
                self.castling_rights["white"]["king_side"] = False
        elif captured_piece == "bR":
            if (to_row, to_col) == (0, 0):
                self.castling_rights["black"]["queen_side"] = False
            elif (to_row, to_col) == (0, 7):
                self.castling_rights["black"]["king_side"] = False

    def promote_pawn_if_needed(self, pos):
        row, col = pos
        piece = self.board[row][col]
        if piece == "wP" and row == 0:
            self.board[row][col] = "wQ"
        elif piece == "bP" and row == 7:
            self.board[row][col] = "bQ"

    def can_castle_king_side(self, color):
        row = 7 if color == "white" else 0
        king = "wK" if color == "white" else "bK"
        rook = "wR" if color == "white" else "bR"
        opponent = "black" if color == "white" else "white"

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
        row = 7 if color == "white" else 0
        king = "wK" if color == "white" else "bK"
        rook = "wR" if color == "white" else "bR"
        opponent = "black" if color == "white" else "white"

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

    def has_any_legal_moves(self, color):
        original_turn = self.turn
        self.turn = color
        try:
            for from_row in range(8):
                for from_col in range(8):
                    piece = self.board[from_row][from_col]
                    if piece is None or self.get_piece_color(piece) != color:
                        continue
                    for to_row in range(8):
                        for to_col in range(8):
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
        return not self.is_in_check(color) and not self.has_any_legal_moves(color)

    def get_game_status(self):
        if self.is_checkmate("white"):
            return "checkmate_black_wins"
        if self.is_checkmate("black"):
            return "checkmate_white_wins"
        if self.is_stalemate("white") or self.is_stalemate("black"):
            return "stalemate"
        if self.is_in_check(self.turn):
            return f"check_{self.turn}"
        return "ongoing"

    def is_within_bounds(self, row, col):
        return 0 <= row < 8 and 0 <= col < 8

    def get_piece_color(self, piece):
        if piece is None:
            return None
        return "white" if piece.startswith("w") else "black"

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

    def is_legal_move(self, from_pos, to_pos):
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

        piece_type = piece[1]
        basic_legal = False

        if piece_type == "P":
            basic_legal = self.is_legal_pawn_move(from_pos, to_pos, piece, target_piece)
        elif piece_type == "R":
            basic_legal = self.is_legal_rook_move(from_pos, to_pos)
        elif piece_type == "B":
            basic_legal = self.is_legal_bishop_move(from_pos, to_pos)
        elif piece_type == "N":
            basic_legal = self.is_legal_knight_move(from_pos, to_pos)
        elif piece_type == "Q":
            basic_legal = self.is_legal_queen_move(from_pos, to_pos)
        elif piece_type == "K":
            basic_legal = self.is_legal_king_move(from_pos, to_pos)

        if not basic_legal:
            return False

        simulated_board = self.simulate_move(from_pos, to_pos)
        return not self.is_in_check(piece_color, simulated_board)

    # ---------------- Turn Handling ----------------

    def switch_turn(self):
        """Switch active player"""
        self.turn = "black" if self.turn == "white" else "white"

    def get_turn(self):
        return self.turn

    def is_game_over(self):
        return self.is_checkmate("white") or self.is_checkmate("black") or self.is_stalemate("white") or self.is_stalemate("black")

    # ---------------- Debug ----------------

    def print_board(self):
        """Print board to console for debugging"""
        for row in self.board:
            print(row)
        print()