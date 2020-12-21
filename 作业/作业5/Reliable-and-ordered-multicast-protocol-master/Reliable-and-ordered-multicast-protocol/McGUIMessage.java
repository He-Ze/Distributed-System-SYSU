
import java.util.Objects;
import java.util.UUID;


/**
 * Message used for McGUImulticast
 *
 * @author Julia Gustafsson & Gebrecherkos Haylay
 */
public class McGUIMessage extends Message  {
        
	//Text of message
    private String text;
   
	//If the message can be delivered or not
     boolean deliverable;
 
	// sequence nr of the message
    private int seqNr;
    
	//The message id of the message
	private int msgID;

	/**
     * Make a new message with the given parameters    
     * @param sender - set the sender id
     * @param msgID -set the message id
     * @param text -set the text
     * @param propSeqNr -set the proposed sequence nr
     */
    public McGUIMessage(int sender, int msgID, String text, int seqNr) {
        super(sender); 
        this.text = text;
        this.deliverable = false;
        this.seqNr = seqNr;
        this.msgID = msgID;
    }
    
    /**
     * Sets the text of the message
     * @param text
     */
    public void setText(String text) {
		this.text = text;
	}


    /**
     * Returns the status of the deliverable of the message.
     */
    public boolean isDeliverable() {
 		return deliverable;
 	}
    
	 /**
     * Returns the final sequence nr of the message.
     */
    public int getSeqNr() {
 		return seqNr;
 	}

    /**
     * Returns the message id of the message.
     */
    public int getMsgID() {
		return msgID;
	}

    
    /**
     * Sets the message id of the message.
     */
	public void setMsgID(int msgID) {
		this.msgID = msgID;
	}

    
    /**
     * Returns the text of the message.
     */
    public String getText() {
        return text;
    }
    
    /**
     * Set the deliverable status of the message
     * @param deliverable - a boolean that indicates if the message is deliverable
     */
    public void setDeliverable(boolean deliverable) {
		this.deliverable = deliverable;
	}
    
    /**
     * Set the final sequence
     * @param seqNR - the new (final) sequence number of the message
     */
    public void setSeqNr(int seqNR) {
 		this.seqNr = seqNR;
 	}

    /**
     * Returns true if the compared message has the same message id, sender and text.
     */
    @Override
    public boolean equals(Object obj) {
    	if(obj == null)
    		return false;
    	if((this == obj))
    		return true;
    	if (obj instanceof McGUIMessage){
    		McGUIMessage m = (McGUIMessage) obj;
    		return (m.getSender() == this.sender && m.getMsgID() == this.msgID &&  text == null ? m.text == null
    		        : text.equals(m.text));
    	}else{
    		return false;
    	}
    }
    	/**
    	 * Return the hashcode for the message
    	 */
    	@Override
    	public int hashCode()
    	{
    	    return  new Integer(this.sender).hashCode() + new Integer(this.msgID).hashCode();
    	}
   
    	
    
    
    public static final long serialVersionUID = 0;
}
