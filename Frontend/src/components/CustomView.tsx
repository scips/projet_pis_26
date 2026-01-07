import { sliceEvents, createPlugin } from '@fullcalendar/core';

function CustomView(props) {
  let segs = sliceEvents(props, true); // allDay=true

  return (
    <>
      <div className='view-title'>
        {props.dateProfile.currentRange.start.toUTCString()}
      </div>
      <div className='view-events'>
        {segs.length} events
      </div>
    </>
  );
}

export default createPlugin({
  views: {
    custom: CustomView
  }
});