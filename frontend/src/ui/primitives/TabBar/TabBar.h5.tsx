/**
 * TabBar — H5 (MUI BottomNavigation + Fab).
 */
import { Box, BottomNavigation, BottomNavigationAction, Fab } from '@mui/material'
import { Home, Kitchen, MenuBook, Person, PhotoCamera } from '@mui/icons-material'
import { tokens } from '../../tokens'
import type { TabBarIconKey, TabBarProps } from './TabBar.types'

function Icon({ iconKey }: { iconKey: TabBarIconKey }) {
  switch (iconKey) {
    case 'home':
      return <Home />
    case 'fridge':
      return <Kitchen />
    case 'recipes':
      return <MenuBook />
    case 'mine':
      return <Person />
  }
}

export default function TabBar(props: TabBarProps) {
  const { items, selected, onSelect, fab } = props
  return (
    <Box>
      <Box
        sx={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          zIndex: tokens.zIndex.bottomNavigation,
        }}
      >
        <BottomNavigation
          value={selected}
          onChange={(_, v) => onSelect(v)}
          showLabels
          sx={{ height: tokens.size.navHeight }}
        >
          {items.map((item) => (
            <BottomNavigationAction
              key={item.key}
              label={item.label}
              icon={<Icon iconKey={item.icon} />}
            />
          ))}
        </BottomNavigation>
      </Box>
      <Fab
        color='primary'
        aria-label={fab.ariaLabel}
        onClick={() => fab.onClick()}
        sx={{
          position: 'fixed',
          left: '50%',
          bottom: tokens.size.navHeight / 2,
          transform: 'translateX(-50%)',
          zIndex: tokens.zIndex.fab,
          width: tokens.size.fab,
          height: tokens.size.fab,
        }}
      >
        <PhotoCamera />
      </Fab>
    </Box>
  )
}
