#!/usr/bin/python

import math
import textwrap
import tcod as libtcod

###############CONSTANTS

#actual size of the window
SCREEN_WIDTH = 80
SCREEN_HEIGHT = 25

# Dungeon generation
MAP_WIDTH = SCREEN_WIDTH
MAP_HEIGHT= SCREEN_HEIGHT - 7
ROOM_MAX_SIZE = 10
ROOM_MIN_SIZE = 6
MAX_ROOMS = 30
MAX_ROOM_MONSTERS = 3
MAX_ROOM_ITEMS = 2

# FOV
FOV_ALGO = 0
FOV_LIGHT_WALLS = True
TORCH_RADIUS = 10

# GUI
BAR_WIDTH = 20
PANEL_HEIGHT = 7
PANEL_Y = SCREEN_HEIGHT - PANEL_HEIGHT
MSG_X = BAR_WIDTH + 2
MSG_WIDTH = SCREEN_WIDTH - BAR_WIDTH - 2
MSG_HEIGHT = PANEL_HEIGHT - 1
INVENTORY_WIDTH = 50

# Game States
game_state = 'playing'
player_action = None

# Items
HEAL_AMOUNT = 4
LIGHTNING_DAMAGE = 20
LIGHTNING_RANGE = 5
CONFUSE_NUM_TURNS = 10
CONFUSE_RANGE = 8

#Colors
color_dark_wall = libtcod.Color(0,0,100)
color_light_wall = libtcod.Color(130,110,50)
color_dark_ground = libtcod.Color(50,50,150)
color_light_ground = libtcod.Color(200,180,50)

LIMIT_FPS = 20  #20 frames-per-second maximum

###############CLASSES

class Rect:
	def __init__(self, x, y, w, h):
		self.x1 = x
		self.y1 = y
		self.x2 = x + w
		self.y2 = y + h
	def center(self):
		center_x = (self.x1 + self.x2) / 2
		center_y = (self.y1 + self.y2) / 2
		return (center_x, center_y)
	def intersect(self, other):
		return (self.x1 <= other.x2 and self.x2 >= other.x1 and
				self.y1 <= other.y2 and self.y2 >= other.y1)

class Tile:
	def __init__(self, blocked, block_sight = None):
		self.blocked = blocked
		if block_sight == None:
			block_sight = blocked
		self.block_sight = block_sight
		self.explored = False

class Object:
	def __init__(self, x, y, char, name, color, blocks=False, fighter=None, ai=None, item=None):
		self.item = item
		if self.item:
			self.item.owner = self
		self.name = name
		self.blocks = blocks
		self.fighter = fighter
		if self.fighter:
			self.fighter.owner = self
		self.ai = ai
		if self.ai:
			self.ai.owner = self
		self.x = x
		self.y = y
		self.char = char
		self.color = color
	def move(self,  dx, dy):
		if not is_blocked(self.x + dx, self.y + dy):
			self.x += dx
			self.y += dy
	def draw(self):
		libtcod.console_set_default_foreground(con, self.color)
		libtcod.console_put_char(con, self.x, self.y, self.char, libtcod.BKGND_NONE)
	def clear(self):
		libtcod.console_put_char(con, self.x, self.y, ' ', libtcod.BKGND_NONE)
	def move_towards(self, target_x, target_y):
		dx = target_x - self.x
		dy = target_y - self.y
		distance = math.sqrt(dx ** 2 + dy ** 2)
		dx = int(round(dx / distance))
		dy = int(round(dy / distance))
		self.move(dx, dy)
	def distance_to(self, other):
		dx = other.x - self.x
		dy = other.y - self.y
		return math.sqrt(dx ** 2 + dy ** 2)
	def send_to_back(self):
		global objects
		objects.remove(self)
		objects.insert(0, self)

class Fighter:
	def __init__(self, hp, defense, power, death_function=None):
		self.death_function = death_function
		self.max_hp = hp
		self.hp = hp
		self.defense = defense
		self.power = power
	def take_damage(self, damage):
		if damage > 0:
			self.hp -= damage
		if self.hp <= 0:
			function = self.death_function
			if function is not None:
				function(self.owner)
	def attack(self, target):
		damage = self.power - target.fighter.defense
		if damage > 0:
			message(self.owner.name.capitalize() + ' attacks ' + target.name + ' for ' + str(damage) + ' hit points.')
			target.fighter.take_damage(damage)
		else:
			message(self.owner.name.capitalize() + ' attacks ' + target.name + ' but it has no effect!')
	def heal(self, amount):
		self.hp += amount
		if self.hp > self.max_hp:
			self.hp = self.max_hp

class BasicMonster:
	def take_turn(self):
		monster = self.owner
		if libtcod.map_is_in_fov(fov_map, monster.x, monster.y):
			if monster.distance_to(player) >= 2:
				monster.move_towards(player.x, player.y)
			elif player.fighter.hp > 0:
				monster.fighter.attack(player)

class ConfusedMonster:
	def __init__(self, old_ai, num_turns=CONFUSE_NUM_TURNS):
		self.old_ai = old_ai
		self.num_turns = num_turns
	def take_turn(self):
		if self.num_turns > 0:
			self.owner.move(libtcod.random_get_int(0, -1, 1), libtcod.random_get_int(0, -1, 1))
			self.num_turns -= 1
		else:
			self.owner.ai = self.old_ai
			message("The " + self.owner.name + " is no longer confused!", libtcod.red)

class Item:
	def __init__(self, use_function=None):
		self.use_function = use_function
	def pick_up(self):
		if len(inventory) >= 26:
			message("Your inventory is full, cannot pick up " + self.owner.name + ".", libtcod.red)
		else:
			inventory.append(self.owner)
			objects.remove(self.owner)
			message("You picked up a " + self.owner.name + "!", libtcod.green)
	def use(self):
		if self.use_function is None:
			message("The " + self.owner.name + " cannot be used.")
		else:
			if self.use_function() != "cancelled":
				inventory.remove(self.owner)

#############FUNCTIONS
def cast_heal():
	if player.fighter.hp == player.fighter.max_hp:
		message("You are already at full health.", libtcod.red)
		return "cancelled"
	message("Your woundes start to feel better!", libtcod.light_violet)
	player.fighter.heal(HEAL_AMOUNT)

def cast_lightning():
	monster = closest_monster(LIGHTNING_RANGE)
	if monster is None:
		message("No enemy is close enough to strike.", libtcod.red)
		return "cancelled"
	message("A lightning bolt strikes the " + monster.name + " with a loud thunder! The damage is " + str(LIGHTNING_DAMAGE) + " hit points.", libtcod.light_blue)
	monster.fighter.take_damage(LIGHTNING_DAMAGE)

def cast_confuse():
	monster = closest_monster(CONFUSE_RANGE)
	if monster is None:
		message("No enemy is close enough to confuse.", libtcod.red)
		return "cancelled"
	old_ai = monster.ai
	monster.ai = ConfusedMonster(old_ai)
	monster.ai.owner = monster
	message("The eyes of the " + monster.name + " look vacant, as it starts to stumble around!", libtcod.light_green)

def closest_monster(max_range):
	closest_enemy = None
	closest_dist = max_range + 1
	for object in objects:
		if object.fighter and not object == player and libtcod.map_is_in_fov(fov_map, object.x, object.y):
			dist = player.distance_to(object)
			if dist < closest_dist:
				closest_enemy = object
				closest_dist = dist
	return closest_enemy

def message(new_msg, color = libtcod.white):
	new_msg_lines = textwrap.wrap(new_msg, MSG_WIDTH)
	for line in new_msg_lines:
		if len(game_msgs) == MSG_HEIGHT:
			del game_msgs[0]
		game_msgs.append((line, color))

def player_death(player):
	global game_state
	message("You died!", libtcod.red)
	game_state = "dead"
	player.char = "%"
	player.color = libtcod.dark_red

def monster_death(monster):
	message(monster.name.capitalize() + " is dead!", libtcod.orange)
	monster.char = "%"
	monster.color = libtcod.dark_red
	monster.blocks = False
	monster.fighter = None
	monster.ai = None
	monster.name = 'remains of ' + monster.name
	monster.send_to_back()

def player_move_or_attack(dx, dy):
	global fov_recompute
	x = player.x + dx
	y = player.y + dy
	target = None
	for object in objects:
		if object.fighter and object.x == x and object.y == y:
			target = object
			break
	if target is not None:
		player.fighter.attack(target)
	else:
		player.move(dx, dy)
		fov_recompute = True

def is_blocked(x, y):
	if map[x][y].blocked:
		return True
	for object in objects:
		if object.blocks and object.x == x and object.y == y:
			return True
	return False

def create_room(room):
	global map
	for x in range(room.x1 + 1, room.x2):
		for y in range(room.y1 + 1, room.y2):
			map[x][y].blocked = False
			map[x][y].block_sight = False

def create_h_tunnel(x1, x2, y):
	global map
	for x in range(min(x1, x2), max(x1, x2) + 1):
		map[x][y].blocked = False
		map[x][y].block_sight = False

def create_v_tunnel(y1, y2, x):
	global map
	for y in range(min(y1, y2), max(y1, y2) + 1):
		map[x][y].blocked = False
		map[x][y].block_sight = False

def make_map():
	global map, player
	map = [[ Tile(True)
		for y in range(MAP_HEIGHT) ]
			for x in range(MAP_WIDTH) ]
	rooms = []
	num_rooms = 0
	for r in range(MAX_ROOMS):
		w = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
		h = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
		x = libtcod.random_get_int(0, 0, MAP_WIDTH - w - 1)
		y = libtcod.random_get_int(0, 0, MAP_HEIGHT - h - 1)
		new_room = Rect(x, y, w, h)
		failed = False
		for other_room in rooms:
			if new_room.intersect(other_room):
				failed = True
				break
		if not failed:
			create_room(new_room)
			(new_x, new_y) = new_room.center()
			if num_rooms == 0:
				player.x = new_x
				player.y = new_y
			else:
				(prev_x, prev_y) = rooms[num_rooms-1].center()
				if libtcod.random_get_int(0, 0, 1) == 1:
					create_h_tunnel(prev_x, new_x, prev_y)
					create_v_tunnel(prev_y, new_y, new_x)
				else:
					create_v_tunnel(prev_y, new_y, prev_x)
					create_h_tunnel(prev_x, new_x, new_y)
			place_objects(new_room)
			rooms.append(new_room)
			num_rooms += 1

def place_objects(room):
	num_monsters = libtcod.random_get_int(0, 0, MAX_ROOM_MONSTERS)
	for i in range(num_monsters):
		x = libtcod.random_get_int(0, room.x1+1, room.x2-1)
		y = libtcod.random_get_int(0, room.y1+1, room.y2-1)
		if not is_blocked(x, y):
			if libtcod.random_get_int(0, 0, 100) < 80:
				fighter_component = Fighter(hp=10, defense=0, power=3, death_function=monster_death)
				ai_component = BasicMonster()
				monster = Object(x, y, 'o', 'orc', libtcod.desaturated_green, blocks=True, fighter=fighter_component, ai=ai_component)
			else:
				fighter_component = Fighter(hp=16, defense=1, power=4, death_function=monster_death)
				ai_component = BasicMonster()
				monster = Object(x, y, 'T', 'troll', libtcod.darker_green, blocks=True, fighter=fighter_component, ai=ai_component)
			objects.append(monster)
	num_items = libtcod.random_get_int(0, 0, MAX_ROOM_ITEMS)
	for i in range(num_items):
		x = libtcod.random_get_int(0, room.x1+1, room.x2-1)
		y = libtcod.random_get_int(0, room.y1+1, room.y2-1)
		if not is_blocked(x, y):
			dice = libtcod.random_get_int(0, 0, 100)
			if dice < 70:
				item_component = Item(use_function=cast_heal)
				item = Object(x, y, "!", "healing potion", libtcod.violet, item=item_component)
			elif dice < 70+15:
				item_component = Item(use_function=cast_lightning)
				item = Object(x,y,'#','scroll of lightning bolt', libtcod.light_yellow, item=item_component)
			else:
				item_component = Item(use_function=cast_confuse)
				item = Object(x,y,'#','scroll of confusion', libtcod.light_yellow, item=item_component)
			objects.append(item)
			item.send_to_back()

def render_all():
	global color_light_wall, color_dark_wall
	global color_light_ground, color_dark_ground
	global fov_recompute
	if fov_recompute:
		fov_recompute = False
		libtcod.map_compute_fov(fov_map, player.x, player.y, TORCH_RADIUS, FOV_LIGHT_WALLS, FOV_ALGO)
	for y in range(MAP_HEIGHT):
		for x in range(MAP_WIDTH):
			visible = libtcod.map_is_in_fov(fov_map, x, y)
			wall = map[x][y].block_sight
			if not visible:
				if map[x][y].explored:
					if wall:
						libtcod.console_set_char_background(con, x, y, color_dark_wall, libtcod.BKGND_SET)
					else:
						libtcod.console_set_char_background(con, x, y, color_dark_ground, libtcod.BKGND_SET)
			else:
				if wall:
					libtcod.console_set_char_background(con, x, y, color_light_wall, libtcod.BKGND_SET)
				else:
					libtcod.console_set_char_background(con, x, y, color_light_ground, libtcod.BKGND_SET)
				map[x][y].explored = True
	for object in objects:
		if libtcod.map_is_in_fov(fov_map, object.x, object.y):
			if object != player:
				object.draw()
	player.draw()

	libtcod.console_blit(con, 0, 0, MAP_WIDTH, MAP_HEIGHT, 0, 0, 0)
	libtcod.console_set_default_foreground(con, libtcod.white)
	libtcod.console_set_default_background(panel, libtcod.black)
	libtcod.console_clear(panel)
	y = 1
	for (line, color) in game_msgs:
		libtcod.console_set_default_foreground(panel, color)
		libtcod.console_print_ex(panel, MSG_X, y, libtcod.BKGND_NONE, libtcod.LEFT, line)
		y += 1
	render_bar(1, 1, BAR_WIDTH, "HP", player.fighter.hp, player.fighter.max_hp, libtcod.light_red, libtcod.darker_red)
	libtcod.console_set_default_foreground(panel, libtcod.light_gray)
	libtcod.console_print_ex(panel, 1, 0, libtcod.BKGND_NONE, libtcod.LEFT, get_names_under_mouse())
	libtcod.console_blit(panel, 0, 0, SCREEN_WIDTH, PANEL_HEIGHT, 0, 0, PANEL_Y)

def handle_keys():
	global fov_recompute, key

	if key.vk == libtcod.KEY_ENTER:
        #Alt+Enter: toggle fullscreen
		libtcod.console_set_fullscreen(not libtcod.console_is_fullscreen())

	elif key.vk == libtcod.KEY_ESCAPE:
		return 'exit'  #exit game

	if game_state == 'playing':
	    #movement keys
		if key.vk == libtcod.KEY_UP:
			player_move_or_attack(0, -1)

		elif key.vk == libtcod.KEY_DOWN:
			player_move_or_attack(0, 1)

		elif key.vk == libtcod.KEY_LEFT:
			player_move_or_attack(-1, 0)

		elif key.vk == libtcod.KEY_RIGHT:
			player_move_or_attack(1, 0)
		else:
			key_char = chr(key.c)
			if key_char == "g":
				for object in objects:
					if object.x == player.x and object.y == player.y and object.item:
						object.item.pick_up()
						break
			if key_char == "i":
				chosen_item = inventory_menu("Press the key next to an item to use it, or any other to cancel.\n")
				if chosen_item is not None:
					chosen_item.use()
			return 'didnt-take-turn'

def menu(header, options, width):
	if len(options) > 26:
		raise ValueError("Cannot have a menu with more than 26 options.")
	header_height = libtcod.console_get_height_rect(con,0,0,width,SCREEN_HEIGHT,header)
	height = len(options) + header_height
	window = libtcod.console_new(width, height)
	libtcod.console_set_default_foreground(window, libtcod.white)
	libtcod.console_print_rect_ex(window,0,0,width,height,libtcod.BKGND_NONE,libtcod.LEFT,header)
	y = header_height
	letter_index = ord('a')
	for option_text in options:
		text = "(" + chr(letter_index) + ") " + option_text
		libtcod.console_print_ex(window,0,y,libtcod.BKGND_NONE, libtcod.LEFT, text)
		y += 1
		letter_index += 1
	x = SCREEN_WIDTH/2 - width/2
	y = SCREEN_HEIGHT/2 - height/2
	libtcod.console_blit(window, 0, 0, width, height, 0, x, y, 1.0, 0.7)
	libtcod.console_flush()
	key = libtcod.console_wait_for_keypress(True)
	index = key.c - ord('a')
	if index >= 0 and index < len(options):
		return index
	return None

def inventory_menu(header):
	if len(inventory) == 0:
		options = ['Inventory is empty']
	else:
		options = [item.name for item in inventory]
	index = menu(header, options, INVENTORY_WIDTH)
	if index is None or len(inventory) == 0:
		return None
	return inventory[index].item

def render_bar(x, y, total_width, name, value, maximum, bar_color, back_color):
	bar_width = int(float(value) / maximum * total_width)
	libtcod.console_set_default_background(panel, back_color)
	libtcod.console_rect(panel, x, y, total_width, 1, False,  libtcod.BKGND_SCREEN)
	libtcod.console_set_default_background(panel, bar_color)
	if bar_width > 0:
		libtcod.console_rect(panel, x, y, bar_width, 1, False, libtcod.BKGND_SCREEN)
	libtcod.console_set_default_foreground(panel, libtcod.white)
	libtcod.console_print_ex(panel, x + total_width / 2, y, libtcod.BKGND_NONE, libtcod.CENTER, name + ": " + str(value) + "/" + str(maximum))

def get_names_under_mouse():
	global mouse
	(x, y) = (mouse.cx, mouse.cy)
	names = [obj.name for obj in objects
		if obj.x == x and obj.y == y and libtcod.map_is_in_fov(fov_map, obj.x, obj.y)]
	names = ", ".join(names)
	return names.capitalize()

#############################################
# Initialization & Main Loop
#############################################
libtcod.console_set_custom_font('font-6.png', (libtcod.FONT_TYPE_GREYSCALE | libtcod.FONT_LAYOUT_ASCII_INROW), 0, 0)
libtcod.console_init_root(SCREEN_WIDTH, SCREEN_HEIGHT, 'python/libtcod tutorial', False)
libtcod.sys_set_fps(LIMIT_FPS)
con = libtcod.console_new(MAP_WIDTH, MAP_HEIGHT)
panel = libtcod.console_new(SCREEN_WIDTH, PANEL_HEIGHT)
mouse = libtcod.Mouse()
key = libtcod.Key()

fighter_component = Fighter(hp = 30, defense = 2, power = 5, death_function=player_death)
player = Object(SCREEN_WIDTH/2, SCREEN_HEIGHT/2, '@', 'player', libtcod.white, blocks=True, fighter = fighter_component)
objects = [player]
game_msgs = []
inventory = []
make_map()
fov_map = libtcod.map_new(MAP_WIDTH, MAP_HEIGHT)
fov_recompute = True
for y in range(MAP_HEIGHT):
	for x in range(MAP_WIDTH):
		libtcod.map_set_properties(fov_map, x, y, not map[x][y].block_sight, not map[x][y].blocked)

message("Welcome stranger! Prepare to perish in the Tombs of the Ancient Kings.", libtcod.red)
while not libtcod.console_is_window_closed():
	libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS|libtcod.EVENT_MOUSE,key,mouse)
	render_all()
	libtcod.console_flush()
	for object in objects:
		object.clear()
    #handle keys and exit game if needed
	player_action = handle_keys()
	if player_action == 'exit':
		break
	if game_state == 'playing' and player_action != 'didnt-take-turn':
		for object in objects:
			if object.ai:
				object.ai.take_turn()
